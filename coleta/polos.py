"""Calcula quanto cada POLO produtor (dados\\polos.csv) representa da produção do Brasil, com os dados
oficiais do IBGE (Produção Agrícola Municipal, tabela 1612, média de 2022 a 2024). Grava dados\\polos_culturas.csv.

Culturas que o IBGE não pesquisa por município (cenoura, folhosas, morango...) entram como
"polo conhecido" (sem percentual), a partir da coluna culturas_conhecidas de polos.csv.

Como usar (dentro da pasta do projeto):
    .venv\\Scripts\\python.exe coleta\\polos.py
"""
import gzip
import json
import time
import urllib.request
from pathlib import Path

import pandas as pd

PASTA = Path(__file__).resolve().parent.parent
POLOS = PASTA / "dados" / "polos.csv"
SAIDA = PASTA / "dados" / "polos_culturas.csv"
ANOS = ["2022", "2023", "2024"]
PAM = {"ALHO": 2690, "BATATA": 2695, "BATATA DOCE": 2694, "CEBOLA": 2697, "TOMATE": 2715, "MELANCIA": 2709, "MILHO VERDE": 83377}
URL = ("https://servicodados.ibge.gov.br/api/v3/agregados/1612/periodos/{anos}/variaveis/214"
       "?localidades=N6[all]&classificacao=81[{cod}]")


def baixar(cod):
    with urllib.request.urlopen(URL.format(anos="|".join(ANOS), cod=cod), timeout=180) as r:
        bruto = r.read()
    if bruto[:2] == b"\x1f\x8b":  # às vezes o IBGE responde compactado (gzip)
        bruto = gzip.decompress(bruto)
    d = json.loads(bruto)
    linhas = []
    for s in d[0]["resultados"][0]["series"]:
        for ano, v in s["serie"].items():
            if v.replace(".", "").isdigit():
                linhas.append({"municipio": s["localidade"]["nome"], "ano": ano, "t": float(v)})
    return pd.DataFrame(linhas)


def main():
    polos = pd.read_csv(POLOS, sep=";", dtype=str).fillna("")
    mapa = {m: p for p, ms in zip(polos["polo"], polos["municipios"]) for m in ms.split("|")}
    linhas, achados = [], set()
    for prod, cod in PAM.items():
        d = baixar(cod)
        if d.empty:
            print(f"{prod}: o IBGE não devolveu dados para {ANOS[0]}-{ANOS[-1]}, pulei")
            continue
        achados |= set(d["municipio"]) & set(mapa)
        tot = d.groupby("ano")["t"].sum()
        d["polo"] = d["municipio"].map(mapa)
        por = d.dropna(subset=["polo"]).groupby(["polo", "ano"])["t"].sum().unstack("ano").reindex(columns=tot.index).fillna(0)
        part = (por / tot).mean(axis=1)
        for polo, v in part.items():
            if v >= 0.005:  # polos com pelo menos 0,5% da produção do país
                linhas.append({"polo": polo, "produto": prod, "participacao": round(v, 4),
                               "fonte": f"IBGE PAM tabela 1612, média {ANOS[0]}-{ANOS[-1]}"})
        print(f"{prod}: Brasil {tot.mean():,.0f} t/ano | " +
              "; ".join(f"{p} {v:.1%}" for p, v in part.sort_values(ascending=False).head(5).items()))
        time.sleep(1)
    for _, p in polos.iterrows():
        for prod in filter(None, p["culturas_conhecidas"].split("|")):
            if prod not in PAM:
                linhas.append({"polo": p["polo"], "produto": prod, "participacao": "",
                               "fonte": "Polo conhecido; o IBGE não mede esta cultura por município (a confirmar)"})
    faltam = sorted(set(mapa) - achados)
    if faltam:
        print("Municípios de polos.csv sem produção destas culturas no IBGE (ou com nome diferente):", ", ".join(faltam))
    pd.DataFrame(linhas).to_csv(SAIDA, sep=";", index=False, encoding="utf-8")
    print(f"Gravado {SAIDA.name}: {len(linhas)} linhas")


if __name__ == "__main__":
    main()
