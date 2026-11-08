"""Importa para o banco 2 arquivos oficiais da Conab (cópias do Internet Archive), sem alterar os originais:

- PrecosMensalUF.txt  -> tabela preco_produtor  (preço recebido pelo produtor / atacado / varejo, por UF e mês)
- ProhortMensal.txt   -> tabela oferta_mensal   (kg e R$ que chegaram às Ceasas de BH, Rio e SP, por cidade de origem)

Como usar (dentro da pasta do projeto):
    .venv\\Scripts\\python.exe coleta\\importar_conab_arquivo.py
"""
import sqlite3
from pathlib import Path

import pandas as pd

PASTA = Path(__file__).resolve().parent.parent
ARQ = PASTA / "dados" / "conab_arquivo"
BANCO = PASTA / "dados" / "precos.db"
CEASAS = ["CEASAMINAS - BELO HORIZONTE", "CEASA/RJ - RIO DE JANEIRO", "CEAGESP - SAO PAULO"]
# Nomes do ProhortMensal (variedades) -> nome padrão usado no painel
PRODUTOS = {"CENOURA": "CENOURA", "ALHO": "ALHO", "CEBOLA": "CEBOLA", "BATATA": "BATATA", "TOMATE": "TOMATE",
            "BETERRABA": "BETERRABA", "REPOLHO": "REPOLHO", "ALFACE": "ALFACE", "MANDIOQUINHA": "MANDIOQUINHA"}


def ler(nome):
    d = pd.read_csv(ARQ / nome, sep=";", encoding="latin-1", dtype=str)
    for c in d.columns:
        d[c] = d[c].str.strip()
    return d


def main():
    pu = ler("PrecosMensalUF.txt")
    pu = pd.DataFrame({
        "produto": pu["produto"], "classificacao": pu["classificao_produto"], "uf": pu["uf"],
        "mes": pu["ano"] + "-" + pu["mes"].str.zfill(2), "nivel": pu["dsc_nivel_comercializacao"],
        "preco_kg": pu["valor_produto_kg"].str.replace(",", ".").astype(float),
    })

    pm = ler("ProhortMensal.txt")
    pm["produto"] = pm["dsc_produto"].str.split().str[0].map(PRODUTOS)
    pm = pm[pm["dsc_ceasa"].isin(CEASAS) & pm["produto"].notna()].copy()
    pm["kg"] = pd.to_numeric(pm["qtd_comercializada_kg"].str.replace(",", "."), errors="coerce")
    pm["valor"] = pd.to_numeric(pm["valor_comercializado"].str.replace(",", "."), errors="coerce")
    pm["mes"] = pm["id_ano_comercializacao"] + "-" + pm["id_mes_comercializacao"].str.zfill(2)
    of = (pm.groupby(["dsc_ceasa", "produto", "mes", "municipio_origem_produto", "uf_origem_produto"], as_index=False)
          [["kg", "valor"]].sum()
          .rename(columns={"dsc_ceasa": "ceasa", "municipio_origem_produto": "origem", "uf_origem_produto": "uf_origem"}))

    with sqlite3.connect(BANCO) as con:
        pu.to_sql("preco_produtor", con, if_exists="replace", index=False)
        of.to_sql("oferta_mensal", con, if_exists="replace", index=False)
    print(f"preco_produtor: {len(pu):,} linhas | {pu['mes'].min()} a {pu['mes'].max()} | níveis: {sorted(pu['nivel'].unique())}")
    print(f"oferta_mensal: {len(of):,} linhas | {of['mes'].min()} a {of['mes'].max()} | produtos: {sorted(of['produto'].unique())}")
    sg = of[of["origem"].str.contains("GOTARDO", na=False)].groupby("produto")["kg"].sum().sort_values(ascending=False) / 1e6
    print("Total vindo de São Gotardo (mil toneladas, 2022-2024):", sg.round(1).to_dict())


if __name__ == "__main__":
    main()
