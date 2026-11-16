"""IPH CeasaMinas-UFV (Índice de Preços de Hortigranjeiros, entreposto de Contagem-MG): lê os boletins mensais (PDF).

Grava duas coisas:
- fatores_mensal: variação do índice no mês (IPH_GERAL, IPH_FRUTAS, IPH_HORTALICAS, IPH_OVOS e subgrupos), em %.
- precos_mensal: preço (R$/kg) dos 58 produtos da cesta NO FIM do mês de referência — não é a média do mês.
  Por isso fica com um nome de Ceasa próprio (CEASAMINAS - CONTAGEM (IPH)) e não se mistura com a média
  mensal da CeasaMinas (coleta\\ceasaminas.py).

Lê só os boletins ainda não lidos. Como usar (dentro da pasta do projeto):
    .venv\\Scripts\\python.exe coleta\\iph.py
Fonte: dee.ufv.br (DEE-UFV e CeasaMinas), dados públicos; citar a fonte.
"""
import io
import json
import re
import sqlite3
from datetime import date, datetime

from pypdf import PdfReader

from boletim_conab import BANCO, MESES, PASTA, baixar, sem_acento

LOG = PASTA / "dados" / "log_iph.txt"
LISTA = "https://dee.ufv.br/wp-json/wp/v2/media?search=Boletim-IPH&per_page=100&_fields=source_url"
CEASA = "CEASAMINAS - CONTAGEM (IPH)"
F_PRECO = "IPH CeasaMinas-UFV — preço no fim do mês de referência (R$/kg)"
F_INDICE = "IPH CeasaMinas-UFV — boletim mensal"


def registrar(msg):
    linha = f"{datetime.now():%Y-%m-%d %H:%M} {msg}"
    print(linha)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(linha + "\n")


def num(t):
    return float(t.replace(".", "").replace(",", "."))


def ler(texto):
    """Do texto do boletim: ({indicador: % no mês}, {produto: R$/kg no fim do período})."""
    ind, precos = {}, {}
    for linha in texto.splitlines():
        linha = linha.strip()
        m = re.match(r"^(IPH(?:/.+?)?)\s+(-?\d+,\d+)%$", linha)
        if m:
            chave = re.sub(r"[^A-Z0-9]+", "_", sem_acento(m.group(1))).strip("_")
            ind.setdefault("IPH_GERAL" if chave == "IPH" else chave, num(m.group(2)))  # vale a 1ª tabela do boletim
            continue
        m = re.match(r"^(\D+?)\s+\d+,\d{2}\s+(\d+,\d{2})\s+-?\d+,\d{2}\s+0,\d{4}$", linha)  # produto, antes, depois, var, peso
        if m:
            precos[sem_acento(m.group(1))] = num(m.group(2))
    return ind, precos


_EX = "IPH -9,65%\nIPH/Hortaliças - fruto -32,26%\nIPH/Frutas 3,00%\nCENOURA 5,17 3,30 -36,13 0,0327\nFrutas 0,3740 10,36% 3,8737"
assert ler(_EX) == ({"IPH_GERAL": -9.65, "IPH_HORTALICAS_FRUTO": -32.26, "IPH_FRUTAS": 3.0}, {"CENOURA": 3.30}), ler(_EX)


def mes_do_arquivo(url):
    m = re.search(r"Boletim-IPH-([a-z]+)(\d{4})", url)
    return f"{m.group(2)}-{MESES[m.group(1)]:02d}" if m and m.group(1) in MESES else None


def main():
    con = sqlite3.connect(BANCO)
    try:
        con.execute("CREATE TABLE IF NOT EXISTS fatores_mensal (produto TEXT, mes TEXT, valor REAL, unidade TEXT, fonte TEXT)")
        con.execute("CREATE TABLE IF NOT EXISTS precos_mensal (produto TEXT, ceasa TEXT, mes TEXT, preco REAL, unidade TEXT, fonte TEXT)")
        con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_pm ON precos_mensal (fonte, ceasa, produto, mes)")
        con.execute("CREATE TABLE IF NOT EXISTS boletim_conab_lidos (url TEXT PRIMARY KEY, linhas INTEGER, lido_em TEXT)")
        lidos = {r[0] for r in con.execute("SELECT url FROM boletim_conab_lidos")}
        urls = sorted(x["source_url"] for x in json.loads(baixar(LISTA)) if x["source_url"] not in lidos)
        for u in urls:
            arq, mes = u.rsplit("/", 1)[-1], mes_do_arquivo(u)
            try:
                assert mes, "não achei o mês no nome do arquivo"
                ind, precos = ler("\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(baixar(u))).pages))
            except Exception as e:
                registrar(f"ERRO {arq}: {type(e).__name__}: {str(e)[:150]}")
                continue
            for k, v in ind.items():
                con.execute("DELETE FROM fatores_mensal WHERE produto = ? AND mes = ?", (k, mes))
                con.execute("INSERT INTO fatores_mensal VALUES (?, ?, ?, '% no mês', ?)", (k, mes, v, F_INDICE))
            con.executemany("INSERT OR REPLACE INTO precos_mensal VALUES (?, ?, ?, ?, 'KG', ?)",
                            [(p, CEASA, mes, v, F_PRECO) for p, v in precos.items()])
            con.execute("INSERT OR REPLACE INTO boletim_conab_lidos VALUES (?, ?, ?)", (u, len(ind) + len(precos), date.today().isoformat()))
            con.commit()
            registrar(f"{arq} ({mes}): {len(ind)} indicadores, {len(precos)} preços" + ("  <- NADA LIDO, formato diferente?" if not ind and not precos else ""))
        registrar(f"IPH: {len(urls)} boletins novos")
    finally:
        con.close()


if __name__ == "__main__":
    main()
