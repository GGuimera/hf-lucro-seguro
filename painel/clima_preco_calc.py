"""Contas da prova "o clima nos polos explica o preço?" (usadas pela página clima_preco.py).

Ideia, em linguagem simples:
1. CLIMA: para cada mês, quanto os polos de uma cultura ficaram fora do normal (chuva, dias de geada,
   dias de calor forte). Cada polo pesa pela parte que tem na produção do Brasil (IBGE).
2. PREÇO: quanto o preço (sem o efeito da época) ficou acima ou abaixo da média dos 3 meses anteriores,
   no mesmo mês do clima, 1 mês depois e 2 meses depois.
3. PROVA: correlação de Spearman + teste de "deslocar o calendário" (compara com o clima de outros meses,
   que não pode ter causado aquele preço) + correção para muitos testes (Benjamini-Hochberg).
"""
import sqlite3

import numpy as np
import pandas as pd

import modelo as M

POLOS_CULT = M.PASTA / "dados" / "polos_culturas.csv"
LIMITES = M.PASTA / "dados" / "clima_limites.csv"
VARIAVEIS = {"chuva": "Chuva fora do normal", "geada": "Dias de geada fora do normal", "calor": "Dias de calor forte fora do normal"}
DEFASAGENS = {0: "no mesmo mês", 1: "1 mês depois", 2: "2 meses depois"}


def pesos_polos(produto):
    """Peso de cada polo na cultura: parte da produção nacional (IBGE) ou, sem dado, pesos iguais nos polos conhecidos."""
    pc = pd.read_csv(POLOS_CULT, sep=";")
    p = pc[pc["produto"] == produto]
    if p.empty:
        return pd.Series(dtype=float), ""
    if p["participacao"].notna().any():
        w = p.dropna(subset=["participacao"]).set_index("polo")["participacao"].astype(float)
        return w / w.sum(), f"pesos pela produção (IBGE): {w.sum():.0%} do Brasil nestes polos"
    w = pd.Series(1.0, index=p["polo"])
    return w / w.sum(), "pesos iguais nos polos conhecidos (o IBGE não mede esta cultura por município)"


def clima_mensal(polos, limites):
    """Anomalias mensais por polo: chuva (desvio padronizado), dias de geada e de calor (menos a média do mês)."""
    with sqlite3.connect(M.BANCO) as con:
        q = ",".join("?" * len(polos))
        h = pd.read_sql(f"SELECT polo, data, tmax, tmin, chuva FROM clima_diario WHERE polo IN ({q})", con, params=list(polos))
    if h.empty:
        return pd.DataFrame()
    h["periodo"] = pd.to_datetime(h["data"]).dt.to_period("M")
    g = h.groupby(["polo", "periodo"]).agg(chuva=("chuva", "sum"), dias=("chuva", "size"),
                                           geada=("tmin", lambda s: (s <= limites["geada_tmin"]).sum()),
                                           calor=("tmax", lambda s: (s >= limites["calor_tmax"]).sum())).reset_index()
    g = g[g["dias"] >= 25]  # só meses completos
    g["mes"] = g["periodo"].dt.month
    clim = g.groupby(["polo", "mes"])[["chuva", "geada", "calor"]].agg(["mean", "std"])
    out = []
    for (polo, mes), grp in g.groupby(["polo", "mes"]):
        c = clim.loc[(polo, mes)]
        out.append(pd.DataFrame({
            "polo": polo, "periodo": grp["periodo"],
            # chuva: desvio padronizado (desvio mínimo de 10 mm para não exagerar nos meses secos)
            "chuva": (grp["chuva"] - c[("chuva", "mean")]) / max(c[("chuva", "std")], 10.0),
            "geada": grp["geada"] - c[("geada", "mean")],
            "calor": grp["calor"] - c[("calor", "mean")],
        }))
    return pd.concat(out, ignore_index=True)


def indice_clima(produto, lim):
    """Anomalia de clima ponderada pelos polos da cultura, mês a mês."""
    w, txt = pesos_polos(produto)
    if w.empty or produto not in lim.index:
        return pd.DataFrame(), txt
    a = clima_mensal(list(w.index), lim.loc[produto])
    if a.empty:
        return a, txt
    a["w"] = a["polo"].map(w)
    idx = a.groupby("periodo").apply(lambda g: pd.Series({v: np.average(g[v], weights=g["w"]) for v in VARIAVEIS}),
                                      include_groups=False)
    return idx.sort_index(), txt


def serie_preco(mensal, pl, produto):
    """Preço mensal sem o efeito da época: a base do modelo (planilha) ou a média do Brasil."""
    mod = M.modelo_produto(mensal, pl, produto)
    if mod is None:
        return pd.Series(dtype=float), ""
    if mod["n_series"] == 1:
        s, onde = list(mod["series"].values())[0], mod["fonte"]
    else:
        b = mensal[(mensal["produto"] == produto) & (mensal["ceasa"] == M.BRASIL)]
        if b.empty:
            return pd.Series(dtype=float), ""
        s, onde = b.set_index("periodo")["preco"], "Média do Brasil (todas as Ceasas, Conab)"
    s = M._continua(s.dropna())
    return s / np.array([mod["indice"][p.month] for p in s.index]), onde


def resposta_preco(adj, k):
    """Preço do mês t+k (sem época) contra a média dos 3 meses antes de t, em %."""
    out = {}
    for t in adj.index:
        ant = adj[(adj.index >= t - 3) & (adj.index < t)].dropna()
        if len(ant) >= 2 and (t + k) in adj.index and pd.notna(adj[t + k]):
            out[t] = adj[t + k] / ant.mean() - 1
    return pd.Series(out, dtype=float)


def _spearman(x, y):
    return float(pd.Series(x).rank().corr(pd.Series(y).rank()))


def teste_deslocamento(x, y):
    """Correlação observada e a chance de achar uma tão forte comparando com o clima de outros meses
    (deslocando o calendário do clima; mantém a 'memória' natural das séries)."""
    n = len(x)
    rho = _spearman(x, y)
    xs = np.asarray(x)
    nulos = [abs(_spearman(np.roll(xs, s), y)) for s in range(6, n - 5)]
    p = (1 + sum(v >= abs(rho) for v in nulos)) / (1 + len(nulos)) if nulos else np.nan
    return rho, p


def benjamini_hochberg(p):
    p = np.asarray(p, dtype=float)
    ok = ~np.isnan(p)
    q = np.full_like(p, np.nan)
    if ok.sum():
        pv = p[ok]
        ordem = np.argsort(pv)
        m = len(pv)
        ajust = pv[ordem] * m / np.arange(1, m + 1)
        ajust = np.minimum.accumulate(ajust[::-1])[::-1]
        tmp = np.empty(m)
        tmp[ordem] = np.minimum(ajust, 1)
        q[ok] = tmp
    return q


def meses_extremos(x, y, quantil=0.85):
    """Preço depois dos meses mais extremos de clima (15% mais altos) contra os demais."""
    corte = x.quantile(quantil)
    alto = y[x >= corte]
    resto = y[x < corte]
    return alto, resto


def testar(mensal, pl, produto, lim):
    """Todas as combinações (variável de clima × defasagem) para uma cultura."""
    clima, txt_pesos = indice_clima(produto, lim)
    adj, onde = serie_preco(mensal, pl, produto)
    linhas = []
    if clima.empty or adj.empty:
        return pd.DataFrame(), txt_pesos, onde, clima, adj
    for k in DEFASAGENS:
        y = resposta_preco(adj, k)
        for v in VARIAVEIS:
            comum = clima.index.intersection(y.index)
            x_, y_ = clima.loc[comum, v], y[comum]
            if len(comum) < 24 or x_.std() == 0:
                continue
            rho, p = teste_deslocamento(x_.values, y_.values)
            alto, resto = meses_extremos(x_, y_)
            linhas.append({"produto": produto, "variavel": v, "k": k, "n": len(comum), "rho": rho, "p": p,
                           "ext_media": alto.mean(), "ext_n": len(alto), "resto_media": resto.mean(),
                           "ini": comum.min(), "fim": comum.max()})
    return pd.DataFrame(linhas), txt_pesos, onde, clima, adj
