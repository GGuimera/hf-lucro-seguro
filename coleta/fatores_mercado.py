"""Coleta FATORES DE MERCADO E DE OFERTA (séries mensais) e grava na tabela fatores_mensal do banco:

- NOAA: índice ONI (El Niño / La Niña). Cada valor é a média de 3 meses; fica anotado no mês do meio.
- IBGE IPCA (tabela 7060): variação mensal do preço ao consumidor, por produto, desde 2020.
- Banco Central (SGS 1635): IPCA de alimentação e bebidas.
- IBGE LSPA (tabela 6588): produção e área plantada. ATENÇÃO: o valor de cada mês é a ESTIMATIVA DA SAFRA
  DO ANO INTEIRO feita naquele mês (não é a produção do mês). Não tem cenoura; alho e cebola param em 12/2017.
- Comex Stat (MDIC): importação de alho e de cebola, em kg e em dólar (FOB).

Tabela fatores_mensal (produto, mes, valor, unidade, fonte) — mesmo formato da agro_mensal.

Como usar (dentro da pasta do projeto):
    .venv\\Scripts\\python.exe coleta\\fatores_mercado.py
Todos são dados públicos oficiais; citar a fonte.
"""
import json
import re
import sqlite3
import unicodedata
import urllib.request
from datetime import date

import pandas as pd

from commodities import BANCO, UA, baixar, registrar, sgs

SIDRA = "https://apisidra.ibge.gov.br/values"
IPCA_ITENS = "7171,7200,7202,7212,7215,7216,7241,7242,7254,7418"  # domicílio, tubérculos, batata, tomate, cebola, cenoura...
LSPA_ITENS = ("39448,39458,39470,39450,39451,39452,39443,39441,39442,"  # alho, cebola, tomate, batata 1-3, soja, milho 1-2
              "39436,39437,39438,39445,39432,39454,39455,39463,39449")   # feijão 1-3, trigo, arroz, café (2), laranja, banana
NCM = {"07032090": "ALHO", "07031019": "CEBOLA"}
TRIMESTRES = ["DJF", "JFM", "FMA", "MAM", "AMJ", "MJJ", "JJA", "JAS", "ASO", "SON", "OND", "NDJ"]


def nome(txt):
    """'1103044.Cenoura' -> 'CENOURA'; '5 Batata - inglesa (1ª Safra)' -> 'BATATA_INGLESA_1A_SAFRA'."""
    txt = re.sub(r"^[\d./]+\s*", "", txt)
    txt = unicodedata.normalize("NFKD", txt).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "_", txt).strip("_").upper()


def tabela(produto, mes, valor, unidade, fonte):
    return pd.DataFrame({"produto": produto, "mes": mes, "valor": valor, "unidade": unidade, "fonte": fonte})


def oni():
    linhas = baixar("https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt").decode().split("\n")[1:]
    reg = [x.split() for x in linhas if x.strip()]
    meses = [f"{ano}-{TRIMESTRES.index(tri) + 1:02d}" for tri, ano, _, _ in reg]
    t = tabela("ENSO_ONI", meses, [float(r[3]) for r in reg], "°C (anomalia, média de 3 meses)", "NOAA/CPC — Oceanic Niño Index")
    assert t.set_index("mes")["valor"]["1997-12"] > 2, "ONI: o El Niño forte de 1997 não apareceu — o formato do arquivo mudou?"
    return t


def sidra(caminho):
    d = pd.DataFrame(json.loads(baixar(f"{SIDRA}/{caminho}"))[1:])
    d["valor"] = pd.to_numeric(d["V"], errors="coerce")  # '...' e '-' = sem dado
    d["mes"] = d["D3C"].str[:4] + "-" + d["D3C"].str[4:]
    return d.dropna(subset=["valor"])


def ipca_itens():
    d = sidra(f"t/7060/n1/all/v/63/p/all/c315/{IPCA_ITENS}")
    return tabela("IPCA_" + d["D4N"].map(nome), d["mes"], d["valor"], "% no mês", "IBGE — IPCA (SIDRA tabela 7060)")


def ipca_alimentos():
    s = sgs(1635)
    return tabela("IPCA_ALIMENTACAO_E_BEBIDAS", s.index, s.values, "% no mês", "Banco Central (SGS 1635)")


def lspa():
    d = sidra(f"t/6588/n1/all/v/35,109/p/all/c48/{LSPA_ITENS}")
    tipo = d["D2C"].map({"35": "LSPA_PRODUCAO_", "109": "LSPA_AREA_PLANTADA_"})
    return tabela(tipo + d["D4N"].map(nome), d["mes"], d["valor"], d["MN"].str.lower() + " (estimativa da safra do ano)",
                  "IBGE — LSPA (SIDRA tabela 6588)")


def comex():
    corpo = json.dumps({"flow": "import", "monthDetail": True, "period": {"from": "2010-01", "to": f"{date.today():%Y-%m}"},
                        "filters": [{"filter": "ncm", "values": list(NCM)}], "details": ["ncm"],
                        "metrics": ["metricFOB", "metricKG"]}).encode()
    req = urllib.request.Request("https://api-comexstat.mdic.gov.br/general", data=corpo,
                                 headers={**UA, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        d = pd.DataFrame(json.loads(r.read())["data"]["list"])
    d["mes"] = d["year"] + "-" + d["monthNumber"]
    p = d["coNcm"].map(NCM)
    fonte = "MDIC — Comex Stat (NCM " + d["coNcm"] + ")"
    return pd.concat([tabela("IMPORTACAO_KG_" + p, d["mes"], d["metricKG"].astype(float), "kg", fonte),
                      tabela("IMPORTACAO_USD_" + p, d["mes"], d["metricFOB"].astype(float), "US$ FOB", fonte)])


def main():
    partes, erros = [], 0
    for f in (oni, ipca_itens, ipca_alimentos, lspa, comex):
        try:
            t = f()
            assert len(t), "veio vazio"
            partes.append(t)
            registrar(f"fatores {f.__name__}: {t['produto'].nunique()} séries, {t['mes'].min()} a {t['mes'].max()}")
        except Exception as e:
            erros += 1
            registrar(f"ERRO fatores {f.__name__}: {type(e).__name__}: {str(e)[:200]}")
    if partes:
        tudo = pd.concat(partes, ignore_index=True)
        prods = list(tudo["produto"].unique())  # só o que chegou hoje: fonte fora do ar mantém os dados antigos
        con = sqlite3.connect(BANCO)
        try:
            con.execute("CREATE TABLE IF NOT EXISTS fatores_mensal (produto TEXT, mes TEXT, valor REAL, unidade TEXT, fonte TEXT)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_fatores ON fatores_mensal (produto, mes)")
            con.execute("CREATE TEMP TABLE chegou (produto TEXT)")
            con.executemany("INSERT INTO chegou VALUES (?)", [(p,) for p in prods])
            con.execute("DELETE FROM fatores_mensal WHERE produto IN (SELECT produto FROM chegou)")
            tudo.to_sql("fatores_mensal", con, if_exists="append", index=False)
            con.commit()
            registrar(f"fatores_mensal: {len(tudo):,} linhas, {len(prods)} séries")
        finally:
            con.close()
    registrar(f"fatores: fim, {erros} erros")


if __name__ == "__main__":
    main()
