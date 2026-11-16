"""Checks the public site data: the own spreadsheet goes online with its real values (R$/kg), unchanged.
Run (inside the project folder, after coleta\\exportar_online.py):
    .venv\\Scripts\\python.exe tests\\teste_publicacao.py
"""
import sqlite3
from pathlib import Path

import pandas as pd

PASTA = Path(__file__).resolve().parent.parent
banco = pd.read_sql("SELECT produto, mes, preco, ceasa FROM planilha_bh",
                    sqlite3.connect(f"file:{PASTA / 'dados' / 'precos.db'}?mode=ro", uri=True))
publicada = pd.read_parquet(PASTA / "online" / "planilha_bh.parquet")

assert "relativo" not in publicada.columns, "a planilha publicada ainda está como desenho"
chave = ["produto", "mes", "ceasa"]
junta = banco.merge(publicada[chave + ["preco"]], on=chave, how="outer", suffixes=("_banco", "_online"), indicator=True)
assert (junta["_merge"] == "both").all(), f"{(junta['_merge'] != 'both').sum()} meses diferentes entre banco e site"
assert (junta["preco_banco"] - junta["preco_online"]).abs().max() < 1e-9, "preços publicados diferem do banco"
assert publicada["preco"].mean() > 1, "valores parecem ser índice (média ~1), não R$"

print(f"ok: {len(publicada)} meses da planilha publicados com os valores reais do banco")
