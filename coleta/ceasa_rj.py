"""Boletim DIÁRIO de preços da Ceasa-RJ (unidade Grande Rio), PDF oficial em rj.gov.br/ceasa -> Cotação.

Guarda tudo na tabela ceasa_rj (preço mínimo, mais comum e máximo por embalagem, e o mais comum em R$/kg).
Depois calcula o preço do mês (mediana do R$/kg mais comum) de um tipo representativo de cada produto (MAPA)
e compara com a Conab nos meses em que as duas fontes existem. Só vão para a tabela precos_mensal (que
continua os gráficos do Rio depois de jan/2026) os produtos que batem com a Conab: pelo menos 6 meses em
comum e diferença de até 10%. A comparação fica em dados\\ceasa_rj_validacao.csv.

Só lê o formato novo do boletim (em uso pelo menos desde 12/2024). Lê só os boletins ainda não lidos.
Como usar (dentro da pasta do projeto):
    .venv\\Scripts\\python.exe coleta\\ceasa_rj.py            (do mês do último boletim lido em diante)
    .venv\\Scripts\\python.exe coleta\\ceasa_rj.py 2025-01    (desde o mês informado)
"""
import io
import re
import sqlite3
import sys
import time
import urllib.parse
from datetime import date, datetime

import pandas as pd
from pypdf import PdfReader

from boletim_conab import BANCO, MESES, PASTA, baixar, sem_acento

LOG = PASTA / "dados" / "log_ceasa_rj.txt"
VALIDACAO = PASTA / "dados" / "ceasa_rj_validacao.csv"
SITE = "https://www.rj.gov.br/"
COTACAO = SITE + "ceasa/Cota%C3%A7%C3%A3o"
INICIO = "2025-01"
CEASA = "CEASA/RJ - RIO DE JANEIRO"
FONTE = "Ceasa-RJ — boletim diário (preço mais comum, mediana do mês, R$/kg)"
PAUSA = 0.5
LINHA = re.compile(r"^(.+?)\s+(?:S/C|-?[\d.]+,\d+%?)\s+([\d.]+,\d{2})\s+([\d.]+,\d{2})\s+([\d.]+,\d{2})$")
PESO = re.compile(r"(?:(\d+(?:,\d+)?)\s*)?kg\b", re.I)
# produto do sistema -> começo da descrição no boletim (sem acento, maiúsculas): um tipo representativo de cada
MAPA = {
    "ABOBORA": "ABOBORA JAPONESA", "ABOBRINHA": "ABOBRINHA ITALIANA", "ALFACE": "ALFACE CRESPA", "ALHO": "ALHO NACIONAL ROXO",
    "BATATA": "BATATA LISA", "BATATA DOCE": "BATATA DOCE", "BERINJELA": "BERINJELA", "BETERRABA": "BETERRABA",
    "BROCOLO": "BROCOLIS AMERICANA", "CARA": "CARA ", "CEBOLA": "CEBOLA NACIONAL BRANCA", "CENOURA": "CENOURA",
    "CHUCHU": "CHUCHU", "COUVE": "COUVE COMUM", "COUVE-FLOR": "COUVE-FLOR", "INHAME": "INHAME CHINES", "JILO": "JILO",
    "MANDIOCA": "AIPIM", "MANDIOQUINHA": "BATATA BAROA", "MELANCIA": "MELANCIA", "MELAO AMARELO": "MELAO AMARELO",
    "MILHO VERDE": "MILHO VERDE", "MORANGO": "MORANGO", "PEPINO": "PEPINO COMUM", "PIMENTAO VERDE": "PIMENTAO VERDE",
    "QUIABO": "QUIABO", "REPOLHO": "REPOLHO VERDE", "TOMATE": "TOMATE EXTRA", "VAGEM": "VAGEM MACARRAO",
    "ABACAXI": "ABACAXI PEROLA", "BANANA NANICA": "BANANA NANICA", "BANANA PRATA": "BANANA PRATA", "GOIABA": "GOIABA VERMELHA",
    "LARANJA PERA": "LARANJA PERA", "LIMAO TAHITI": "LIMAO TAITI", "MACA": "MACA NACIONAL GALA", "MAMAO FORMOSA": "MAMAO FORMOSA",
    "MAMAO HAWAY": "MAMAO PAPAYA", "MANGA": "MANGA PALMER", "MARACUJA AZEDO": "MARACUJA", "TANGERINA": "TANGERINA PONKAN",
    "UVA ITALIA": "UVA ITALIA", "UVA NIAGARA": "UVA ROSADA", "UVA RUBI": "UVA RUBI",
}


def registrar(msg):
    linha = f"{datetime.now():%Y-%m-%d %H:%M} {msg}"
    print(linha)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(linha + "\n")


def num(t):
    return float(t.replace(".", "").replace(",", "."))


def ler(texto):
    """Do texto do boletim: (data 'AAAA-MM-DD', [(descrição, mínimo, comum, máximo, R$/kg do comum ou None)]).
    Pula linhas sem cotação e erros de digitação (preço comum fora da faixa mínimo–máximo)."""
    d = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", texto)
    if not d or "MODAL" not in texto:
        return None, []
    saida = {}
    for linha in texto.splitlines():
        m = LINHA.match(linha.strip())
        if not m:
            continue
        mn, comum, mx = (num(x) for x in m.groups()[1:])
        if not (0 < mn <= comum <= mx):
            continue
        p = PESO.search(m.group(1))
        kg = (num(p.group(1)) if p.group(1) else 1.0) if p else None
        saida[m.group(1)] = (m.group(1), mn, comum, mx, round(comum / kg, 4) if kg else None)
    return f"{d.group(3)}-{int(d.group(2)):02d}-{int(d.group(1)):02d}", list(saida.values())


_EX = ("Dia Semana: sexta-feira 13/11/2026\nMIN MODAL MAX\nCENOURA Extra A Cx 20 kg -46,43% 45,00 50,00 55,00\n"
       "ABÓBORA Baiana kg 5,00% 2,00 2,50 3,00\nESPINAFRE Mol 0,5 kg 8900,00% 1,50 180,00 2,00\nCAJÁ S/C 70,00 80,00 90,00\n"
       "LARANJA KINKAN IMPORTADA Cx 2,0 kg / 4 band 0,5 kg -6,67% 75,00 80,00 90,00\nALCACHOFRA Cx 2 kg S/C\n"
       "OVO BRANCO Cx 30 dz -36,87% 145,00 150,00 155,00")
assert ler(_EX) == ("2026-11-13", [("CENOURA Extra A Cx 20 kg", 45.0, 50.0, 55.0, 2.5), ("ABÓBORA Baiana kg", 2.0, 2.5, 3.0, 2.5),
                                   ("CAJÁ", 70.0, 80.0, 90.0, None),  # sem peso na embalagem: não dá para saber o R$/kg
                                   ("LARANJA KINKAN IMPORTADA Cx 2,0 kg / 4 band 0,5 kg", 75.0, 80.0, 90.0, 40.0),
                                   ("OVO BRANCO Cx 30 dz", 145.0, 150.0, 155.0, None)]), ler(_EX)  # espinafre (erro) e alcachofra (S/C) fora


def links(url):
    """[(endereço completo, texto do link)] de uma página."""
    html = baixar(url).decode("utf-8", "replace")
    return [(urllib.parse.urljoin(SITE, urllib.parse.quote(urllib.parse.unquote(h), safe="/:")),
             re.sub(r"<[^>]+>|&nbsp;", "", t).strip()) for h, t in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, re.S)]


def boletins(desde):
    """Endereços dos PDFs dos meses a partir de 'AAAA-MM' (página Cotação -> ano -> mês)."""
    for pag_ano, ano in links(COTACAO):
        if not re.fullmatch(r"20\d\d", ano) or ano < desde[:4]:
            continue
        for pag_mes, nome in links(pag_ano):
            mes = MESES.get(sem_acento(nome).lower())
            if mes and f"{ano}-{mes:02d}" >= desde:
                yield from sorted({u for u, _ in links(pag_mes) if u.lower().endswith(".pdf")})


def coletar(con, desde):
    lidos = {r[0] for r in con.execute("SELECT url FROM boletim_conab_lidos")}
    novos = [u for u in boletins(desde) if u not in lidos]
    registrar(f"Ceasa-RJ: {len(novos)} boletins novos desde {desde}")
    total = 0
    for i, u in enumerate(novos, 1):
        arq = urllib.parse.unquote(u).rsplit("/", 1)[-1]
        try:
            dia, linhas = ler("\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(baixar(u))).pages))
        except Exception as e:  # rede instável ou PDF quebrado: registra e segue (tenta de novo na próxima vez)
            registrar(f"ERRO {arq}: {type(e).__name__}: {str(e)[:150]}")
            continue
        con.executemany("INSERT OR REPLACE INTO ceasa_rj VALUES (?, ?, ?, ?, ?, ?)", [(dia, *x) for x in linhas])
        con.execute("INSERT OR REPLACE INTO boletim_conab_lidos VALUES (?, ?, ?)", (u, len(linhas), date.today().isoformat()))
        con.commit()
        total += len(linhas)
        if not linhas:
            registrar(f"{arq}: nada lido (formato diferente?)")
        elif i % 25 == 0:
            registrar(f"  {i}/{len(novos)} boletins, até {dia}")
        time.sleep(PAUSA)
    registrar(f"Ceasa-RJ: {total} preços gravados")


def mensal(con):
    """Preço do mês por produto do MAPA, comparação com a Conab e gravação do que bate."""
    d = pd.read_sql("SELECT data, descricao, quilo FROM ceasa_rj WHERE quilo IS NOT NULL", con)
    if d.empty:
        return
    d["chave"], d["mes"] = d["descricao"].map(sem_acento), d["data"].str[:7]
    c = pd.read_sql("SELECT produto, substr(data, 1, 7) AS mes, preco FROM precos WHERE ceasa = ? AND unidade = 'KG' AND data >= ?",
                    con, params=(CEASA, d["data"].min()[:7] + "-01"))
    conab = c.groupby(["produto", "mes"])["preco"].median()
    resumo, gravar = [], []
    for prod, comeco in MAPA.items():
        g = d[d["chave"].str.startswith(comeco)]
        dia = g.groupby(["mes", "data"])["quilo"].median()                      # 2 embalagens no mesmo dia -> mediana
        m = dia.groupby("mes").agg(["median", "size"])
        rj = m.loc[m["size"] >= 5, "median"]                                    # mês com menos de 5 dias não é confiável
        comum = rj.index.intersection(conab[prod].index) if prod in conab.index.get_level_values(0) else []
        razao = float((rj[comum] / conab[prod][comum]).median()) if len(comum) else float("nan")
        bate = len(comum) >= 6 and 0.9 <= razao <= 1.1
        resumo.append({"produto": prod, "tipo_no_boletim": comeco.strip(), "meses_rj": len(rj), "meses_em_comum": len(comum),
                       "rj_sobre_conab": round(razao, 3), "entra_nos_graficos": "sim" if bate else "não"})
        if bate:
            gravar += [(prod, CEASA, mes, round(float(v), 4), "KG", FONTE) for mes, v in rj.items()]
    con.execute("DELETE FROM precos_mensal WHERE fonte = ?", (FONTE,))
    con.executemany("INSERT INTO precos_mensal VALUES (?, ?, ?, ?, ?, ?)", gravar)
    con.commit()
    r = pd.DataFrame(resumo)
    r.to_csv(VALIDACAO, sep=";", index=False, encoding="utf-8")
    registrar(f"Ceasa-RJ mensal: {(r['entra_nos_graficos'] == 'sim').sum()} de {len(r)} produtos batem com a Conab; "
              f"{len(gravar)} preços mensais gravados (detalhe em dados\\{VALIDACAO.name})")


def main():
    con = sqlite3.connect(BANCO)
    try:
        con.execute("CREATE TABLE IF NOT EXISTS ceasa_rj (data TEXT, descricao TEXT, preco_min REAL, preco_comum REAL, "
                    "preco_max REAL, quilo REAL, PRIMARY KEY (data, descricao))")
        con.execute("CREATE TABLE IF NOT EXISTS precos_mensal (produto TEXT, ceasa TEXT, mes TEXT, preco REAL, unidade TEXT, fonte TEXT)")
        con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_pm ON precos_mensal (fonte, ceasa, produto, mes)")
        con.execute("CREATE TABLE IF NOT EXISTS boletim_conab_lidos (url TEXT PRIMARY KEY, linhas INTEGER, lido_em TEXT)")
        ult = con.execute("SELECT MAX(data) FROM ceasa_rj").fetchone()[0]
        coletar(con, sys.argv[1] if len(sys.argv) > 1 else (ult[:7] if ult else INICIO))
        mensal(con)
    finally:
        con.close()


if __name__ == "__main__":
    main()
