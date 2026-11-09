"""Preço médio MENSAL (R$/kg) das principais hortaliças e frutas em 10 Ceasas, tirado do Boletim Hortigranjeiro
mensal da Conab (PDF oficial). Grava na tabela precos_mensal (fonte = Conab boletim). Cada boletim traz o mês
anterior (ex.: o de setembro traz agosto). Lê só os boletins ainda não lidos.

Como usar (dentro da pasta do projeto):
    .venv\\Scripts\\python.exe coleta\\boletim_conab.py
"""
import io
import re
import sqlite3
import unicodedata
import urllib.request
from datetime import date, datetime
from pathlib import Path

from pypdf import PdfReader

PASTA = Path(__file__).resolve().parent.parent
BANCO = PASTA / "dados" / "precos.db"
LOG = PASTA / "dados" / "log_boletim_conab.txt"
BASE = "https://www.gov.br/conab/pt-br/atuacao/informacoes-agropecuarias/hortigranjeiros-prohort/boletim-hortigranjeiro"
MESES = {m: i for i, m in enumerate(["janeiro", "fevereiro", "marco", "abril", "maio", "junho", "julho", "agosto",
                                      "setembro", "outubro", "novembro", "dezembro"], 1)}
FONTE = "Conab — Boletim Hortigranjeiro (preço médio do mês, R$/kg)"


def registrar(msg):
    linha = f"{datetime.now():%Y-%m-%d %H:%M} {msg}"
    print(linha)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(linha + "\n")


def sem_acento(t):
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().upper().strip()


def baixar(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (PrecoSeguro)"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def ler_tabelas(texto):
    """Do texto de uma página: [(mes 'AAAA-MM', ceasa, produto, preco)] das tabelas 'Produto A B C D E'."""
    m = re.search(r"Preços médios em (\w+) de (\d{4})", texto)
    if not m or sem_acento(m.group(1)).lower() not in MESES:
        return []
    mes = f"{m.group(2)}-{MESES[sem_acento(m.group(1)).lower()]:02d}"
    saida, produtos = [], None
    for linha in texto.splitlines():
        linha = linha.strip()
        if linha.startswith("Produto "):
            produtos = [sem_acento(p) for p in linha.split()[1:]]
            continue
        r = re.match(r"^(CEA\S*(?: - |\s)[^\d]+?)\s+((?:(?:[\d.]+,\d{2}|-)\s+(?:-?[\d.]+,\d{2}%|-)\s*)+)$", linha)
        if produtos and r:
            nums = r.group(2).split()[0::2]  # preço, variação, preço, variação...
            for prod, v in zip(produtos, nums):
                if v != "-":
                    saida.append((mes, sem_acento(r.group(1)), prod, float(v.replace(".", "").replace(",", "."))))
    return saida


_EX = ("Preços médios em agosto de 2026 das principais hortaliças\nProduto Alface Batata Cebola Cenoura Tomate\n"
       "Ceasa Preço Ago/Jul Preço Ago/Jul Preço Ago/Jul Preço Ago/Jul Preço Ago/Jul\n"
       "CEASAMINAS - Belo Horizonte 9,41 -4,47% 2,27 -15,16% 3,55 -16,52% 3,18 -1,39% 3,06 23,45%\n"
       "Média Ponderada 5,06 -14,80% 2,63 -11,60% 3,88 -13,80% 4,05 0,88% 4,03 18,13%")
assert ler_tabelas(_EX)[3] == ("2026-08", "CEASAMINAS - BELO HORIZONTE", "CENOURA", 3.18), ler_tabelas(_EX)
assert len(ler_tabelas(_EX)) == 5  # a linha "Média Ponderada" fica de fora


def pdfs_do_ano(ano):
    pagina = baixar(BASE).decode("utf-8", "replace")
    sub = re.findall(rf'href="({re.escape(BASE)}/{ano}/[^"]+)"', pagina)
    if not sub:
        return []
    html = baixar(sub[0]).decode("utf-8", "replace")
    return sorted(set(re.findall(r'href="([^"]+\.pdf)"', html)))


def main():
    con = sqlite3.connect(BANCO)
    try:
        con.execute("CREATE TABLE IF NOT EXISTS precos_mensal (produto TEXT, ceasa TEXT, mes TEXT, preco REAL, "
                    "unidade TEXT, fonte TEXT)")
        con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_pm ON precos_mensal (fonte, ceasa, produto, mes)")
        con.execute("CREATE TABLE IF NOT EXISTS boletim_conab_lidos (url TEXT PRIMARY KEY, linhas INTEGER, lido_em TEXT)")
        lidos = {r[0] for r in con.execute("SELECT url FROM boletim_conab_lidos")}
        hoje = date.today()
        urls = [u for a in (hoje.year - 1, hoje.year) for u in pdfs_do_ano(a) if u not in lidos]
        total = 0
        for u in urls:
            try:
                leitor = PdfReader(io.BytesIO(baixar(u)))
                linhas = [x for p in leitor.pages for x in ler_tabelas(p.extract_text() or "")]
            except Exception as e:
                registrar(f"ERRO {u.rsplit('/', 1)[-1]}: {type(e).__name__}: {str(e)[:150]}")
                continue
            con.executemany("INSERT OR REPLACE INTO precos_mensal VALUES (?, ?, ?, ?, 'KG', ?)",
                            [(p, c, m, v, FONTE) for m, c, p, v in linhas])
            con.execute("INSERT OR REPLACE INTO boletim_conab_lidos VALUES (?, ?, ?)", (u, len(linhas), hoje.isoformat()))
            con.commit()
            total += len(linhas)
            registrar(f"{u.rsplit('/', 1)[-1]}: {len(linhas)} preços" + (" (tabela não encontrada)" if not linhas else ""))
        registrar(f"boletim Conab: {len(urls)} boletins novos, {total} preços gravados")
    finally:
        con.close()


if __name__ == "__main__":
    main()
