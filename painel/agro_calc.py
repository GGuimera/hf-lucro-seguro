"""Contas da aba "Agro: commodities" (usadas pela página agro.py). Mesmo método do HF:

1. Preço "de hoje": cada mês é corrigido pela inflação (IPCA) até o último mês disponível.
2. Época do preço: preço do mês ÷ média móvel de 12 meses em volta dele (tira a tendência de alta/queda
   de longo prazo). A média desses índices por mês do ano mostra os meses caros e os baratos.
3. Teste justo (como no HF): para cada ano, os meses da estratégia B são escolhidos SÓ com os outros anos.
   - Estocáveis (grãos e café): A = vender tudo na colheita; B = guardar e vender nos melhores meses,
     pagando o custo de guardar (armazém + dinheiro parado) por mês.
   - Fluxo (pecuária, açúcar, etanol): A = vender igual nos 12 meses; B = concentrar nos melhores meses.
   - Insumos (fertilizantes, diesel): A = comprar nos meses de costume; B = comprar nos meses mais baratos,
     pagando o custo de comprar antes (dinheiro parado) até o mês em que o insumo é usado.
4. Clima × preço: a mesma prova da página do HF (clima_preco_calc), com os polos do agro.
"""
import sqlite3

import numpy as np
import pandas as pd

import modelo as M

LISTA = M.PASTA / "dados" / "commodities.csv"
CUSTOS = M.PASTA / "dados" / "custos_agro.csv"
POLOS = M.PASTA / "dados" / "polos_agro.csv"
LIMITES = M.PASTA / "dados" / "clima_limites_agro.csv"


def carregar():
    lista = pd.read_csv(LISTA, sep=";", dtype=str).fillna("")
    with sqlite3.connect(M.BANCO) as con:
        tabs = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        mensal = pd.read_sql("SELECT * FROM agro_mensal", con) if "agro_mensal" in tabs else pd.DataFrame()
        diario = (pd.read_sql("SELECT produto, data, valor FROM agro_diario WHERE data >= date('now', '-400 days')", con)
                  if "agro_diario" in tabs else pd.DataFrame())
    custos = pd.read_csv(CUSTOS, sep=";") if CUSTOS.exists() else pd.DataFrame()
    return lista, mensal, diario, custos


def ipca_fator(mensal):
    """Fator para levar cada mês ao R$ do último mês com IPCA (meses depois dele ficam com fator 1)."""
    ind = mensal[mensal["produto"] == "IPCA_INDICE"].set_index("mes")["valor"].sort_index()
    if ind.empty:
        return lambda meses: np.ones(len(meses)), ""
    ultimo = ind.index[-1]

    def f(meses):
        v = ind.reindex(meses).ffill()
        v = v.fillna(ind.iloc[-1])
        return (ind.iloc[-1] / v).values
    return f, ultimo


def serie(mensal, produto, real=True):
    s = mensal[mensal["produto"] == produto].set_index("mes")["valor"].sort_index()
    s.index = pd.PeriodIndex(s.index, freq="M")
    s = s[~s.index.duplicated()]
    if real and len(s):
        f, _ = ipca_fator(mensal)
        s = s * f([p.strftime("%Y-%m") for p in s.index])
    return s


def indices(s):
    """Índice de época de cada mês (preço ÷ média móvel centrada de 12 meses)."""
    s = s.asfreq("M") if isinstance(s.index, pd.PeriodIndex) else s
    mm = s.rolling(12, center=True, min_periods=10).mean()
    mm = mm.rolling(2, min_periods=1).mean()  # média 2×12 (centrada de verdade)
    r = (s / mm).dropna()
    tab = pd.DataFrame({"ano": r.index.year, "mes": r.index.month, "r": r.values})
    por_mes = tab.groupby("mes")["r"].agg(["mean", "count", "std"])
    por_mes["mean"] = por_mes["mean"] / por_mes["mean"].mean()
    acima = tab.assign(acima=tab["r"] > 1).groupby("mes")["acima"].mean()
    por_mes["vezes_acima"] = acima
    return por_mes.reindex(range(1, 13)), tab.pivot(index="ano", columns="mes", values="r")


def _escolher(rel, outros, k, maior=True):
    m = rel.loc[outros].mean()
    m = m.dropna()
    return list((m.sort_values(ascending=not maior)).head(k).index)


def teste_justo(s, tipo, meses_a, k, taxa, mes_alvo=None):
    """Devolve (tabela por ano com A, B e diferença, contagem dos meses escolhidos, meses escolhidos com todos os anos).
    s = preço real mensal. Valores em R$ da unidade do produto (estocável/fluxo: preço líquido recebido;
    insumo: preço líquido pago)."""
    s = s.asfreq("M")
    linhas, rel, net = {}, {}, {}
    if tipo == "estocavel":
        h0 = meses_a[0]
        for ano in range(s.index.year.min(), s.index.year.max() + 1):
            ini = pd.Period(f"{ano}-{h0:02d}", "M")
            janela = s.reindex(pd.period_range(ini, periods=12, freq="M"))
            if janela.isna().sum() > 1:
                continue
            janela = janela.interpolate(limit_direction="both")
            liquido = janela.values * (1 - taxa * np.arange(12))  # guardar o mês o custa "taxa" do valor
            a = liquido[: len(meses_a)].mean()
            net[ano] = pd.Series(liquido, index=range(12))
            rel[ano] = net[ano] / a
            linhas[ano] = a
        rotulo = lambda o: M.MESES[(h0 - 1 + o) % 12]
        maior = True
    elif tipo == "insumo":
        alvo = mes_alvo or 9
        for ano in range(s.index.year.min() + 1, s.index.year.max() + 1):
            fim = pd.Period(f"{ano}-{alvo:02d}", "M")
            janela = s.reindex(pd.period_range(fim - 11, fim, freq="M"))
            if janela.isna().sum() > 1:
                continue
            janela = janela.interpolate(limit_direction="both")
            meses_antes = np.arange(11, -1, -1)
            liquido = janela.values * (1 + taxa * meses_antes)  # comprar antes: dinheiro parado até o uso
            idx = [((alvo - 1 - mb) % 12) + 1 for mb in meses_antes]
            sr = pd.Series(liquido, index=idx)
            a = sr.loc[meses_a].mean()
            net[ano] = sr
            rel[ano] = sr / a
            linhas[ano] = a
        rotulo = lambda m: M.MESES[m - 1]
        maior = False
    else:  # fluxo / referência: ano civil
        for ano in range(s.index.year.min(), s.index.year.max() + 1):
            janela = s.reindex(pd.period_range(f"{ano}-01", periods=12, freq="M"))
            if janela.isna().sum() > 1:
                continue
            janela = janela.interpolate(limit_direction="both")
            sr = pd.Series(janela.values, index=range(1, 13))
            a = sr.mean()
            net[ano] = sr
            rel[ano] = sr / a
            linhas[ano] = a
        rotulo = lambda m: M.MESES[m - 1]
        maior = True
    if len(rel) < 3:
        return pd.DataFrame(), {}, [], rotulo
    rel = pd.DataFrame(rel).T
    net = pd.DataFrame(net).T
    a = pd.Series(linhas)
    b, contagem = {}, {}
    for ano in rel.index:
        esc = _escolher(rel, rel.index.drop(ano), k, maior)
        b[ano] = net.loc[ano, esc].mean()
        for m in esc:
            contagem[m] = contagem.get(m, 0) + 1
    b = pd.Series(b)
    tab = pd.DataFrame({"A": a, "B": b})
    tab["dif"] = (tab["B"] - tab["A"]) if maior else (tab["A"] - tab["B"])  # sempre: positivo = B foi melhor
    todos = _escolher(rel, rel.index, k, maior)
    return tab, contagem, todos, rotulo


def resumo_teste(dif):
    n, k = len(dif), int((dif > 0).sum())
    lo, hi = M.intervalo_bootstrap(dif.values)
    p = min(1.0, 2 * M.chance_acaso(max(k, n - k), n)) if n else float("nan")
    if n < 5:
        v = "Inconclusivo: poucos anos"
    elif lo > 0:
        v = "B é melhor — diferença consistente"
    elif hi < 0:
        v = "A é melhor — diferença consistente"
    else:
        v = "Sem diferença clara entre A e B"
    return {"n": n, "k": k, "lo": lo, "hi": hi, "p": p, "veredito": v,
            "sem_ext": dif.drop(index=dif.abs().idxmax()).mean() if n > 2 else float("nan"),
            "ano_ext": dif.abs().idxmax() if n else None}


# ---------- unidades ----------
def kg_por_unidade(unidade):
    """Quantos kg tem a unidade de preço ou de produtividade (saca 60 kg, saca 50 kg, tonelada)."""
    u = unidade.lower()
    if "tonelada" in u or "/t" in u or "ton" in u:
        return 1000.0
    for n in (60, 50):
        if f"{n} kg" in u or f"{n}kg" in u:
            return float(n)
    return float("nan")


# ---------- clima × preço ----------
def limites():
    return pd.read_csv(LIMITES, sep=";").set_index("produto")


def prova_clima(mensal, item, lim):
    """Mesma prova do HF: anomalia de clima nos polos do produto (pesos iguais) × preço sem a época."""
    import clima_preco_calc as C
    polos = [p for p in item["polos"].split("|") if p]
    if not polos or item["produto"] not in lim.index:
        return pd.DataFrame(), pd.DataFrame(), pd.Series(dtype=float)
    clima = C.clima_mensal(polos, lim.loc[item["produto"]])
    if clima.empty:
        return pd.DataFrame(), clima, pd.Series(dtype=float)
    idx = clima.groupby("periodo")[list(C.VARIAVEIS)].mean().sort_index()
    s = serie(mensal, item["produto"])
    if len(s) < 36:
        return pd.DataFrame(), idx, pd.Series(dtype=float)
    por_mes, _ = indices(s)
    adj = s / np.array([por_mes.loc[p.month, "mean"] for p in s.index])
    linhas = []
    for k in C.DEFASAGENS:
        y = C.resposta_preco(adj, k)
        for v in C.VARIAVEIS:
            comum = idx.index.intersection(y.index)
            x_, y_ = idx.loc[comum, v], y[comum]
            if len(comum) < 24 or x_.std() == 0:
                continue
            rho, p = C.teste_deslocamento(x_.values, y_.values)
            alto, resto = C.meses_extremos(x_, y_)
            linhas.append({"produto": item["produto"], "variavel": v, "k": k, "n": len(comum), "rho": rho, "p": p,
                           "ext_media": alto.mean(), "ext_n": len(alto), "resto_media": resto.mean()})
    return pd.DataFrame(linhas), idx, adj


def previsao_polos(polos):
    """Última 'foto' da previsão de 16 dias (3 modelos) gravada pela coleta diária de clima."""
    with sqlite3.connect(M.BANCO) as con:
        tabs = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "previsao_log" not in tabs:
            return pd.DataFrame()
        q = ",".join("?" * len(polos))
        d = pd.read_sql(f"SELECT * FROM previsao_log WHERE polo IN ({q}) AND coletado_em = "
                        f"(SELECT MAX(coletado_em) FROM previsao_log WHERE polo IN ({q}))", con, params=list(polos) * 2)
    return d
