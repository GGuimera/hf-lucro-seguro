"""Prova "os fatores de mercado e de oferta explicam o preço?" — mesmas contas da prova do clima
(clima_preco_calc): Spearman + deslocar o calendário + correção para muitos testes (Benjamini-Hochberg).

As hipóteses (lista HIPOTESES) foram escritas ANTES de olhar os resultados. Não acrescente combinações
depois de ver os números sem contar isso no total de testes.

Como usar (dentro da pasta do projeto; grava dados\\fatores_teste.csv):
    .venv\\Scripts\\python.exe painel\\fatores_calc.py
Os fatores vêm de coleta\\fatores_mercado.py (tabela fatores_mensal) — só existe no computador, não no site.
"""
import sqlite3

import numpy as np
import pandas as pd

import agro_calc as A
import clima_preco_calc as C
import modelo as M

SAIDA = M.PASTA / "dados" / "fatores_teste.csv"
HF = ["ALHO", "CEBOLA", "CENOURA", "BATATA", "TOMATE"]
P = "LSPA_PRODUCAO_"
# (nome do fator, colunas somadas, transformação, [(tipo, produto do preço)], defasagens em meses)
HIPOTESES = [
    ("El Niño (ONI)", ["ENSO_ONI"], "nivel", [("hf", p) for p in HF], (0, 3, 6)),
    ("El Niño (ONI)", ["ENSO_ONI"], "nivel", [("agro", p) for p in ("SOJA", "MILHO", "CAFE_ARABICA", "BOI", "TRIGO", "ARROZ")], (0, 3, 6)),
    ("Importação de alho (kg)", ["IMPORTACAO_KG_ALHO"], "vs12", [("hf", "ALHO")], (0, 1, 2)),
    ("Importação de cebola (kg)", ["IMPORTACAO_KG_CEBOLA"], "vs12", [("hf", "CEBOLA")], (0, 1, 2)),
    ("Dólar", ["DOLAR"], "var3", [("hf", "ALHO")], (0, 1, 2)),
    ("Diesel", ["DIESEL"], "var3", [("hf", p) for p in HF], (0, 1, 2)),
    ("Safra estimada de batata (IBGE)", [P + f"BATATA_INGLESA_{i}A_SAFRA" for i in (1, 2, 3)], "anual", [("hf", "BATATA")], (0, 1, 2)),
    ("Safra estimada de tomate (IBGE)", [P + "TOMATE"], "anual", [("hf", "TOMATE")], (0, 1, 2)),
    ("Safra estimada de soja (IBGE)", [P + "SOJA"], "anual", [("agro", "SOJA")], (0, 1, 2)),
    ("Safra estimada de milho (IBGE)", [P + "MILHO_1A_SAFRA", P + "MILHO_2A_SAFRA"], "anual", [("agro", "MILHO")], (0, 1, 2)),
    ("Safra estimada de trigo (IBGE)", [P + "TRIGO"], "anual", [("agro", "TRIGO")], (0, 1, 2)),
    ("Safra estimada de arroz (IBGE)", [P + "ARROZ"], "anual", [("agro", "ARROZ")], (0, 1, 2)),
    ("Safra estimada de café arábica (IBGE)", [P + "CAFE_ARABICA"], "anual", [("agro", "CAFE_ARABICA")], (0, 1, 2)),
]
TRANSFORMA = {
    "nivel": lambda s: s,                                        # o próprio valor
    "var3": lambda s: s / s.shift(3) - 1,                        # variação em 3 meses
    "vs12": lambda s: s / s.rolling(12).mean().shift(1) - 1,     # contra a média dos 12 meses anteriores
    "anual": lambda s: s / s.shift(12) - 1,                      # contra o mesmo mês do ano anterior
}


def fatores():
    """Tabela mês × fator (inclui dólar e diesel, que já estavam na agro_mensal)."""
    with sqlite3.connect(M.BANCO) as con:
        t = pd.concat([pd.read_sql("SELECT produto, mes, valor FROM fatores_mensal", con),
                       pd.read_sql("SELECT produto, mes, valor FROM agro_mensal WHERE produto IN ('DOLAR', 'DIESEL')", con)])
    t = t.pivot_table(index="mes", columns="produto", values="valor")
    t.index = pd.PeriodIndex(t.index, freq="M")
    t = t.reindex(pd.period_range(t.index.min(), t.index.max(), freq="M"))
    imp = [c for c in t.columns if c.startswith("IMPORTACAO_")]  # mês sem registro no Comex = não importou
    t[imp] = t[imp].where(t[imp].notna() | t[imp].bfill().isna() | t[imp].ffill().isna(), 0)
    return t


def precos():
    """Função que devolve o preço mensal sem o efeito da época (HF: base do modelo; agro: Cepea em R$ de hoje)."""
    _, mensal, _, pl, _, _ = M.carregar()
    _, am, _, _ = A.carregar()

    def adj(tipo, produto):
        if tipo == "hf":
            return C.serie_preco(mensal, pl, produto)[0]
        s = A.serie(am, produto)
        if len(s) < 36:
            return pd.Series(dtype=float)
        por_mes, _ = A.indices(s)
        return s / np.array([por_mes.loc[p.month, "mean"] for p in s.index])
    return adj


def testar_tudo():
    F, adj = fatores(), precos()
    linhas = []
    for nome, cols, transf, alvos, defasagens in HIPOTESES:
        x = TRANSFORMA[transf](F[cols].sum(axis=1, min_count=len(cols))).replace([np.inf, -np.inf], np.nan).dropna()
        for tipo, produto in alvos:
            a = adj(tipo, produto)
            for k in defasagens:
                y = C.resposta_preco(a, k) if len(a) else pd.Series(dtype=float)
                comum = x.index.intersection(y.index)
                x_, y_ = x[comum], y[comum]
                if len(comum) < 24 or x_.std() == 0:
                    linhas.append({"fator": nome, "produto": produto, "k": k, "n": len(comum)})  # fica visível que não deu para testar
                    continue
                rho, p = C.teste_deslocamento(x_.values, y_.values)
                alto, resto = C.meses_extremos(x_, y_)
                linhas.append({"fator": nome, "produto": produto, "k": k, "n": len(comum), "rho": rho, "p": p,
                               "ext_media": alto.mean(), "resto_media": resto.mean(), "ini": comum.min(), "fim": comum.max()})
    R = pd.DataFrame(linhas)
    R["q"] = C.benjamini_hochberg(R["p"])
    return R


if __name__ == "__main__":
    R = testar_tudo()
    R.to_csv(SAIDA, sep=";", index=False, encoding="utf-8")
    pd.set_option("display.width", 250, "display.max_rows", 300)
    print(R.sort_values("p").round(3).to_string(index=False))
    ok = R["p"].notna()
    print(f"\n{len(R)} combinações previstas, {ok.sum()} testadas, {(~ok).sum()} sem dados suficientes (menos de 24 meses em comum).")
    print(f"p < 0,05 sem correção: {(R['p'] < 0.05).sum()}  |  aprovadas com correção (q < 0,10): {(R['q'] < 0.10).sum()}")
