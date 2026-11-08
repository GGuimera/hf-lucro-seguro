"""Coleta as cotações do Entreposto da Capital (CEAGESP - São Paulo) e guarda no banco.

Como usar (dentro da pasta do projeto):
    .venv\\Scripts\\python.exe coleta\\ceagesp.py 2026-01-01 2026-11-07

Consulta segundas, quartas e sextas (dias de boletim); se não houver boletim,
tenta o dia seguinte. Espera 2 s entre pedidos para não sobrecarregar o site.
Pode ser interrompido e rodado de novo: pula o que já foi coletado.
"""
import html
import re
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

PASTA = Path(__file__).resolve().parent.parent
BANCO = PASTA / "dados" / "precos.db"
URL = "https://ceagesp.gov.br/cotacoes/"
CATEGORIAS = ["FRUTAS", "LEGUMES", "VERDURAS", "DIVERSOS"]
PAUSA = 2.0

LINHA = re.compile(r"<tr[^>]*>\s*<td class=\"ta_l\">(.*?)</td>(.*?)</tr>", re.S)
CELULA = re.compile(r"<td[^>]*>(.*?)</td>", re.S)


def numero(txt):
    txt = txt.strip().replace(".", "").replace(",", ".")
    try:
        return float(txt)
    except ValueError:
        return None


def consultar(categoria, dia):
    dados = urllib.parse.urlencode({"cot_grupo": categoria, "cot_data": dia.strftime("%d/%m/%Y")}).encode()
    req = urllib.request.Request(URL, data=dados, headers={"User-Agent": "PrecoSeguro-teste/0.1 (uso pessoal)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        pagina = r.read().decode("utf-8", errors="replace")
    if f"<span> {dia:%d/%m/%Y}</span>" not in pagina:
        return []
    linhas = []
    for nome, resto in LINHA.findall(pagina):
        cel = [html.unescape(re.sub(r"<[^>]+>", "", c)).strip() for c in CELULA.findall(resto)]
        if len(cel) < 6 or nome.strip().startswith("<b>"):
            continue
        linhas.append({
            "data": dia.isoformat(), "categoria": categoria,
            "produto": html.unescape(nome).strip(), "classificacao": cel[0], "unidade": cel[1],
            "preco_min": numero(cel[2]), "preco_comum": numero(cel[3]), "preco_max": numero(cel[4]),
            "quilo": numero(cel[5]),
        })
    return linhas


def preparar(con):
    con.execute("""CREATE TABLE IF NOT EXISTS ceagesp (
        data TEXT, categoria TEXT, produto TEXT, classificacao TEXT, unidade TEXT,
        preco_min REAL, preco_comum REAL, preco_max REAL, quilo REAL,
        PRIMARY KEY (data, categoria, produto, classificacao, unidade))""")
    con.execute("CREATE TABLE IF NOT EXISTS ceagesp_consultas (data TEXT, categoria TEXT, linhas INTEGER, PRIMARY KEY (data, categoria))")


def main(inicio, fim):
    con = sqlite3.connect(BANCO)
    preparar(con)
    feitas = {(d, c) for d, c in con.execute("SELECT data, categoria FROM ceagesp_consultas")}
    dia, total, pedidos = inicio, 0, 0
    while dia <= fim:
        if dia.weekday() in (0, 2, 4):  # segunda, quarta, sexta
            for cat in CATEGORIAS:
                for tentativa in (dia, dia + timedelta(days=1)):
                    if tentativa > fim or tentativa.weekday() > 4:
                        break
                    if (tentativa.isoformat(), cat) in feitas:
                        break
                    try:
                        linhas = consultar(cat, tentativa)
                    except Exception as e:  # rede instável: registra e segue
                        print(f"  ERRO {tentativa} {cat}: {e}")
                        time.sleep(PAUSA * 3)
                        break
                    pedidos += 1
                    con.executemany(
                        "INSERT OR REPLACE INTO ceagesp VALUES (:data,:categoria,:produto,:classificacao,:unidade,"
                        ":preco_min,:preco_comum,:preco_max,:quilo)", linhas)
                    con.execute("INSERT OR REPLACE INTO ceagesp_consultas VALUES (?,?,?)",
                                (tentativa.isoformat(), cat, len(linhas)))
                    con.commit()
                    feitas.add((tentativa.isoformat(), cat))
                    total += len(linhas)
                    time.sleep(PAUSA)
                    if linhas:
                        print(f"{tentativa:%d/%m/%Y} {cat:<9} {len(linhas):>4} preços")
                        break
        dia += timedelta(days=1)
    print(f"FIM: {pedidos} consultas, {total} preços novos.")
    con.close()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Uso: ceagesp.py AAAA-MM-DD AAAA-MM-DD")
    a, b = (datetime.strptime(x, "%Y-%m-%d").date() for x in sys.argv[1:])
    main(a, b)
