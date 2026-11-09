"""Preço médio MENSAL (R$/kg) da CeasaMinas Grande BH, direto do site oficial — o mesmo de onde veio a planilha
de séries históricas. Grava na tabela precos_mensal (fonte = CeasaMinas). O site mostra os últimos 5 anos.

Como usar (dentro da pasta do projeto):
    .venv\\Scripts\\python.exe coleta\\ceasaminas.py          (ano atual e anterior)
    .venv\\Scripts\\python.exe coleta\\ceasaminas.py --tudo   (os 5 anos que o site mostra)
"""
import http.cookiejar
import re
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path

import pandas as pd

PASTA = Path(__file__).resolve().parent.parent
BANCO = PASTA / "dados" / "precos.db"
LOG = PASTA / "dados" / "log_ceasaminas.txt"
URL = "https://minas1.ceasa.mg.gov.br/detec/prc_medio_prd/prc_medio_prd.php"
MERCADO = "214##@@Grande BH - CEAMG"
CEASA = "CEASAMINAS - BELO HORIZONTE"
NOME_SITE = {"MELAO AMARELO": "MELAO", "PIMENTAO VERDE": "PIMENTAO"}  # nomes diferentes no site


def registrar(msg):
    linha = f"{datetime.now():%Y-%m-%d %H:%M} {msg}"
    print(linha)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(linha + "\n")


def ler_meses(html, ano):
    """Pares '01-Janeiro ... 13,48' da tabela de resultado -> {'2026-01': 13.48}."""
    texto = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
    return {f"{ano}-{m}": float(v.replace(".", "").replace(",", "."))
            for m, v in re.findall(r"\b(0[1-9]|1[0-2])-[A-Za-zçÇ]+ (\d{1,3}(?:\.\d{3})*,\d{2})\b", texto)}


assert ler_meses("<td>01-Janeiro</td><td>13,48</td><td>03-Março</td><td>1.013,13</td>", 2026) == \
    {"2026-01": 13.48, "2026-03": 1013.13}


class Sessao:
    def __init__(self):
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.op.addheaders = [("User-Agent", "Mozilla/5.0 (PrecoSeguro)")]

    def pedir(self, dados=None):
        corpo = urllib.parse.urlencode(dados).encode() if dados else None
        with self.op.open(URL, corpo, timeout=60) as r:
            return r.read().decode("utf-8", "replace")


def consultar(produto_opt, ano):
    s = Sessao()
    inicial = s.pedir()
    init = re.search(r'name="script_case_init" value="(\d+)"', inicial).group(1)
    s.pedir({"script_case_init": init, "nmgp_opcao": "busca", "mercado_cond": "eq", "mercado": MERCADO,
             "produto_cond": "ii", "produto": produto_opt, "ano_cond": "eq", "ano": f"{ano}##@@{ano}",
             "NM_operador": "and", "bprocessa": "pesq", "form_condicao": "3"})
    return ler_meses(s.pedir({"script_case_init": init, "nmgp_opcao": "pesq"}), ano)


def main():
    hoje = date.today()
    anos = range(hoje.year - 4, hoje.year + 1) if "--tudo" in sys.argv else (hoje.year - 1, hoje.year)
    opcoes = {n.strip(): v for v, n in re.findall(r'<OPTION value="([A-Z0-9]{3}##@@[^"]+)"\s*>([^<]+)</OPTION>',
                                                   Sessao().pedir())}
    culturas = pd.read_csv(PASTA / "dados" / "culturas.csv", sep=";")["produto"]
    linhas, faltam, erros = [], [], 0
    for prod in culturas:
        opt = opcoes.get(NOME_SITE.get(prod, prod))
        if not opt:
            faltam.append(prod)
            continue
        for ano in anos:
            try:
                for mes, preco in consultar(opt, ano).items():
                    linhas.append({"produto": prod, "ceasa": CEASA, "mes": mes, "preco": preco, "unidade": "KG",
                                   "fonte": "CeasaMinas (preço médio do mês, R$/kg)"})
            except Exception as e:
                erros += 1
                registrar(f"ERRO {prod} {ano}: {type(e).__name__}: {str(e)[:150]}")
            time.sleep(1)
    if faltam:
        registrar("não achei no site: " + ", ".join(faltam))
    if not linhas:
        registrar("nada novo (site fora do ar?)")
        return
    d = pd.DataFrame(linhas)
    con = sqlite3.connect(BANCO)
    try:
        con.execute("CREATE TABLE IF NOT EXISTS precos_mensal (produto TEXT, ceasa TEXT, mes TEXT, preco REAL, "
                    "unidade TEXT, fonte TEXT)")
        con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_pm ON precos_mensal (fonte, ceasa, produto, mes)")
        con.executemany("INSERT OR REPLACE INTO precos_mensal VALUES (?, ?, ?, ?, ?, ?)",
                        d[["produto", "ceasa", "mes", "preco", "unidade", "fonte"]].values.tolist())
        con.commit()
    finally:
        con.close()
    registrar(f"CeasaMinas: {len(d)} meses gravados ({d['mes'].min()} a {d['mes'].max()}), {d['produto'].nunique()} produtos, {erros} erros")


if __name__ == "__main__":
    main()
