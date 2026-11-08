"""Validação geral dos dados do Preço Seguro. Só lê o banco; não altera nada.

Como usar (dentro da pasta do projeto):
    .venv\\Scripts\\python.exe coleta\\validar_dados.py
"""
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

PASTA = Path(__file__).resolve().parent.parent
BANCO = PASTA / "dados" / "precos.db"
PRINCIPAIS = ["CEASAMINAS - BELO HORIZONTE", "CEASA/RJ - RIO DE JANEIRO", "CEAGESP - SAO PAULO"]


def titulo(t):
    print(f"\n{'=' * 8} {t} {'=' * 8}")


def main():
    con = sqlite3.connect(BANCO)
    df = pd.read_sql("SELECT uf, ceasa, produto, unidade, data, preco FROM precos", con)
    df["data"] = pd.to_datetime(df["data"])

    titulo("1. Tamanho e período")
    print(f"Conab: {len(df):,} preços | {df['data'].min():%d/%m/%Y} a {df['data'].max():%d/%m/%Y} | "
          f"{df['ceasa'].nunique()} Ceasas | {df['produto'].nunique()} produtos")
    dup = df.duplicated(["ceasa", "produto", "unidade", "data"]).sum()
    print(f"Registros repetidos (mesma Ceasa, produto, unidade e dia): {dup}")
    fds = df["data"].dt.day_of_week >= 5
    print(f"Preços em sábado ou domingo: {fds.sum():,} ({fds.mean():.1%})")

    titulo("2. Unidades")
    un = df.groupby("produto")["unidade"].nunique()
    for p in un[un > 1].index:
        cont = df[df["produto"] == p].groupby("unidade").size().to_dict()
        print(f"  {p}: unidades diferentes entre Ceasas -> {cont}")
    troca = df.groupby(["ceasa", "produto"])["unidade"].nunique()
    print(f"Ceasa+produto que mudaram de unidade no tempo: {(troca > 1).sum()}")

    titulo("3. Valores fora do padrão (3x acima ou abaixo da mediana de 15 registros vizinhos)")
    df = df.sort_values(["ceasa", "produto", "unidade", "data"])
    med = df.groupby(["ceasa", "produto", "unidade"])["preco"].transform(
        lambda s: s.rolling(15, center=True, min_periods=5).median())
    razao = df["preco"] / med
    fora = df[(razao > 3) | (razao < 1 / 3)].assign(razao=razao)
    print(f"Total: {len(fora):,} de {len(df):,} ({len(fora) / len(df):.2%})")
    princ = fora[fora["ceasa"].isin(PRINCIPAIS)]
    print(f"Nas Ceasas principais (BH, RJ, SP): {len(princ)}")
    if len(princ):
        print(princ.sort_values("razao", key=lambda s: (np.log(s)).abs(), ascending=False)
              .head(10)[["ceasa", "produto", "unidade", "data", "preco", "razao"]].round({"preco": 2, "razao": 2})
              .to_string(index=False))

    titulo("4. Buracos: meses sem nenhum preço (jun/2022 a dez/2025) nas Ceasas principais")
    meses = pd.period_range("2022-06", "2025-12", freq="M")
    for ce in PRINCIPAIS:
        d = df[df["ceasa"] == ce]
        tem = d.groupby("produto")["data"].apply(lambda s: set(s.dt.to_period("M")))
        faltas = {p: len(set(meses) - s) for p, s in tem.items()}
        ruins = {p: f for p, f in faltas.items() if f > 3}
        print(f"  {ce}: {len(tem)} produtos | com mais de 3 meses faltando: {len(ruins)} "
              f"{dict(sorted(ruins.items(), key=lambda x: -x[1])[:6]) if ruins else ''}")

    titulo("5. Ceagesp 2026 (menor <= comum <= maior)")
    cg = pd.read_sql("SELECT * FROM ceagesp", con)
    erro = cg[(cg["preco_min"] > cg["preco_comum"]) | (cg["preco_comum"] > cg["preco_max"])]
    print(f"{len(cg):,} preços | fora da ordem: {len(erro)} | sem preço: {cg['preco_comum'].isna().sum()}")

    titulo("6. Estabilidade da época (o padrão se repete entre metades dos anos?)")
    pl = pd.read_sql("SELECT produto, mes, preco FROM planilha_bh", con)
    pl["ano"], pl["m"] = pl["mes"].str[:4].astype(int), pl["mes"].str[5:].astype(int)
    rj = df[df["ceasa"] == "CEASA/RJ - RIO DE JANEIRO"].assign(ano=lambda x: x["data"].dt.year, m=lambda x: x["data"].dt.month)
    rj = rj.groupby(["produto", "ano", "m"], as_index=False)["preco"].mean()
    for nome, base in [("Planilha BH", pl), ("Conab Rio", rj)]:
        cnt = base.groupby(["produto", "ano"])["m"].transform("count")
        base = base[cnt >= 10].copy()
        base["idx"] = base["preco"] / base.groupby(["produto", "ano"])["preco"].transform("mean")
        for p in sorted(base["produto"].unique()):
            g = base[base["produto"] == p].pivot(index="ano", columns="m", values="idx")
            if len(g) < 2:
                continue
            anos = list(g.index)
            if len(anos) >= 4:
                a, b = g.loc[anos[0::2]].mean(), g.loc[anos[1::2]].mean()
                r = a.corr(b)
                tipo = "anos pares x ímpares da série"
            else:
                r = g.T.corr().values[np.triu_indices(len(g), 1)].mean()
                tipo = "média da correlação entre anos"
            if nome == "Planilha BH" or p in ("ALHO", "CENOURA", "CEBOLA", "TOMATE", "BATATA", "ALFACE", "REPOLHO", "BETERRABA"):
                nivel = "FIRME" if r >= 0.7 else "MÉDIA" if r >= 0.4 else "FRACA"
                print(f"  {nome:<12} {p:<10} {len(anos)} anos | correlação {r:+.2f} ({tipo}) -> época {nivel}")
    con.close()


if __name__ == "__main__":
    main()
