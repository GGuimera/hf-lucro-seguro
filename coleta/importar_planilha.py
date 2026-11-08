"""Importa a planilha mensal de BH (alho, cebola, cenoura, desde 2017) para o banco.

A planilha original NÃO é alterada. Usa a série em sequência (lado direito de cada aba),
que confere 100% com a tabela mês x ano e é a mais completa.

Como usar (dentro da pasta do projeto):
    .venv\\Scripts\\python.exe coleta\\importar_planilha.py
"""
import sqlite3
from pathlib import Path

import pandas as pd

PASTA = Path(__file__).resolve().parent.parent
PLANILHA = PASTA / "dados" / "Séries históricas 2017 alho cenoura e cebola.xlsx"
BANCO = PASTA / "dados" / "precos.db"
# aba -> (produto no padrão Conab, coluna da data, coluna do preço)
ABAS = {"Alho": ("ALHO", 13, 14), "Cebola": ("CEBOLA", 13, 14), "Cenoura": ("CENOURA", 15, 16)}


PASTA_EXTRA = PASTA / "dados" / "planilhas"
BH = "CEASAMINAS - BELO HORIZONTE"


def planilhas_padrao():
    """Lê as planilhas no formato padrão (produto; mes AAAA-MM; preco; ceasa) da pasta dados\\planilhas."""
    lidas = []
    for arq in sorted(PASTA_EXTRA.glob("*")):
        if arq.name.upper().startswith("MODELO") or arq.suffix.lower() not in (".csv", ".xlsx"):
            continue
        d = pd.read_excel(arq, dtype=str) if arq.suffix.lower() == ".xlsx" else pd.read_csv(arq, sep=None, engine="python", dtype=str)
        d.columns = [c.strip().lower() for c in d.columns]
        if not {"produto", "mes", "preco"} <= set(d.columns):
            print(f"  IGNORADO {arq.name}: faltam colunas produto, mes ou preco")
            continue
        d["preco"] = pd.to_numeric(d["preco"].str.replace(",", "."), errors="coerce")
        d["mes"] = pd.to_datetime(d["mes"].str.strip(), format="%Y-%m", errors="coerce").dt.strftime("%Y-%m")
        d["ceasa"] = d["ceasa"].fillna(BH).str.strip().replace("", BH) if "ceasa" in d.columns else BH
        d = d.dropna(subset=["mes", "preco"])
        d["produto"] = d["produto"].str.strip().str.upper()
        d["unidade"], d["fonte"] = "KG", f"Planilha do usuário ({arq.name})"
        print(f"  {arq.name}: {len(d)} meses ({', '.join(sorted(d['produto'].unique()))})")
        lidas.append(d[["produto", "mes", "preco", "unidade", "fonte", "ceasa"]])
    return lidas


def main():
    linhas = []
    for aba, (produto, c_data, c_preco) in ABAS.items():
        d = pd.read_excel(PLANILHA, sheet_name=aba, header=None)
        for i in range(4, len(d)):
            dt, v = d.iloc[i, c_data], d.iloc[i, c_preco]
            if hasattr(dt, "year") and pd.notna(v) and not isinstance(v, str):
                linhas.append({"produto": produto, "mes": f"{dt.year}-{dt.month:02d}", "preco": float(v),
                               "unidade": "KG", "fonte": "Planilha do usuário (CeasaMinas BH)", "ceasa": BH})
    df = pd.DataFrame(linhas)
    extras = planilhas_padrao() if PASTA_EXTRA.exists() else []
    if extras:
        df = pd.concat([df] + extras, ignore_index=True).drop_duplicates(["produto", "mes", "ceasa"], keep="last")
    with sqlite3.connect(BANCO) as con:
        df.to_sql("planilha_bh", con, if_exists="replace", index=False)
    for p, g in df.groupby("produto"):
        print(f"{p:<8} {len(g):>3} meses  de {g['mes'].min()} a {g['mes'].max()}")
    print(f"Total: {len(df)} linhas gravadas na tabela planilha_bh")


if __name__ == "__main__":
    main()
