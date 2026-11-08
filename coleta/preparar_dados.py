"""Lê o arquivo de preços diários da Conab (Prohort) e guarda num banco SQLite.

Como usar (dentro da pasta do projeto):
    .venv\\Scripts\\python.exe coleta\\preparar_dados.py
"""
import sqlite3
import sys
from pathlib import Path

import pandas as pd

PASTA = Path(__file__).resolve().parent.parent
ARQUIVO = PASTA / "dados" / "ProhortDiario_20260102.txt"
BANCO = PASTA / "dados" / "precos.db"


def main():
    if not ARQUIVO.exists():
        sys.exit(f"Arquivo não encontrado: {ARQUIVO}")

    print(f"Lendo {ARQUIVO.name} ...")
    df = pd.read_csv(ARQUIVO, sep=";", encoding="latin-1", dtype=str)

    # Tira espaços sobrando no começo e no fim de cada texto
    for col in df.columns:
        df[col] = df[col].str.strip()

    df = df.rename(columns={
        "municipio_ceasa": "municipio",
        "uf_ceasa": "uf",
        "dsc_ceasa": "ceasa",
        "dsc_produto": "produto",
        "sig_unidade_medida": "unidade",
        "data_preco": "data",
        "preco_diario": "preco",
    }).drop(columns=["cod_ibge_municipio"])

    df["data"] = pd.to_datetime(df["data"].str[:10], format="%Y/%m/%d", errors="coerce")
    df["preco"] = pd.to_numeric(df["preco"], errors="coerce")

    antes = len(df)
    df = df.dropna(subset=["data", "preco"])
    df = df[df["preco"] > 0]
    df = df.drop_duplicates(subset=["ceasa", "produto", "unidade", "data"])
    print(f"Linhas lidas: {antes:,} | linhas válidas: {len(df):,}")

    df["data"] = df["data"].dt.strftime("%Y-%m-%d")
    df["fonte"] = "Conab/Prohort"

    with sqlite3.connect(BANCO) as con:
        df.to_sql("precos", con, if_exists="replace", index=False)
        con.execute("CREATE INDEX IF NOT EXISTS idx_prod ON precos (produto, ceasa, data)")
    print(f"Banco salvo em: {BANCO}")


if __name__ == "__main__":
    main()
