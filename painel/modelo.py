"""Modelo Preditivo Sazonal (MPS) — versão 2. As contas usadas por todas as páginas do painel.

Como funciona, em linguagem simples:
1. Para cada produto montamos uma série MÊS A MÊS contínua (mediana dos preços diários do mês).
   - Alho, cenoura e cebola: sua planilha de BH (2017+), emendada com a Conab BH quando falta mês.
   - Outras culturas: cada Ceasa do país com pelo menos 3 anos de dados (índice combinado).
2. ÉPOCA (índice sazonal): preço do mês ÷ média móvel de 12 meses ao redor dele. Usamos a mediana
   entre anos e Ceasas, o que tira a inflação e os choques isolados.
3. CENÁRIOS: para cada ano do histórico, quanto o preço real nos meses de venda ficou acima ou abaixo
   da TENDÊNCIA de longo prazo. Isso junta a época e o nível do ano (anos bons e ruins), sem contar nada duas vezes.
4. PREÇO NORMAL na Ceasa escolhida: média dos últimos 24 meses sem o efeito da época, corrigida pela
   inflação até a data da venda. Preço esperado = preço normal × cenário.
5. Preço ao produtor = preço na Ceasa × (1 − diferença). Lucro = preço ao produtor × produção vendável − custo.
"""
import math
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

NOME_MODELO = "Modelo Preditivo Sazonal"
VERSAO = "2"
PASTA = Path(__file__).resolve().parent.parent
BANCO = PASTA / "dados" / "precos.db"
CULTURAS = PASTA / "dados" / "culturas.csv"
CUSTOS = PASTA / "dados" / "custos.csv"
PERDAS = PASTA / "dados" / "perdas.csv"

MESES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
MESES_LONGO = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
               "setembro", "outubro", "novembro", "dezembro"]
UNIDADES = {"KG": "kg", "DZ": "dúzia", "UN": "unidade"}
REGIOES = {
    "Alto Paranaíba — São Gotardo / PADAP (MG)": ("cal_altitude_cerrado", "CEASAMINAS - BELO HORIZONTE"),
    "Sul de Minas / Mantiqueira (MG)": ("cal_altitude_fria", "CEASAMINAS - BELO HORIZONTE"),
    "Região Serrana (RJ)": ("cal_altitude_fria", "CEASA/RJ - RIO DE JANEIRO"),
    "Cinturão Verde / Interior (SP)": ("cal_planalto", "CEAGESP - SAO PAULO"),
    "Outra região do Sudeste (calendário geral)": ("cal_planalto", "CEASA/RJ - RIO DE JANEIRO"),
}
DESCONTO_PADRAO = 15      # % que o produtor recebe a menos que a Ceasa (usuário: 10 a 20%, às vezes mais)
INFLACAO_PADRAO = 4.5     # % ao ano, para levar o preço de hoje até a data da venda (estimativa)
QUEDA_FORA_EPOCA = 20     # % de produtividade a menos quando se planta fora da época (estimativa)
BRASIL = "BRASIL - MÉDIA DE TODAS AS CEASAS"
MIN_CEASAS_BRASIL = 5
MIN_MESES_SERIE = 36      # mínimo de meses para uma Ceasa entrar no índice combinado
METODOS = ["Preço normal dos últimos 24 meses (recomendado)", "Tendência de longo prazo", "Último ano completo"]


# ----------------------------------------------------------------- carregamento
def media_brasil(con):
    """Preço médio do dia de todas as Ceasas do país (só a unidade principal; dias com 5+ Ceasas)."""
    b = pd.read_sql(
        "SELECT 'BR' AS uf, ? AS ceasa, produto, unidade, data, AVG(preco) AS preco, COUNT(DISTINCT ceasa) AS n_ceasas "
        "FROM precos GROUP BY produto, unidade, data", con, params=(BRASIL,))
    principal = (b.groupby(["produto", "unidade"]).size().reset_index(name="n")
                 .sort_values("n", ascending=False).drop_duplicates("produto")[["produto", "unidade"]])
    b = b.merge(principal, on=["produto", "unidade"])
    return b[b["n_ceasas"] >= MIN_CEASAS_BRASIL]


@st.cache_data(show_spinner="Carregando preços…")
def carregar():
    """df: preços diários de MG/RJ/SP + média Brasil (para mostrar). mensal: mediana mensal de TODAS as Ceasas."""
    with sqlite3.connect(BANCO) as con:
        todas = pd.read_sql("SELECT uf, ceasa, produto, unidade, data, preco FROM precos", con)
        br = media_brasil(con).drop(columns="n_ceasas")
        tem = con.execute("SELECT name FROM sqlite_master WHERE name='planilha_bh'").fetchone()
        pl = pd.read_sql("SELECT * FROM planilha_bh", con) if tem else pd.DataFrame()
    if len(pl) and "ceasa" not in pl.columns:
        pl["ceasa"] = "CEASAMINAS - BELO HORIZONTE"
    todas = pd.concat([todas, br], ignore_index=True)
    todas["data"] = pd.to_datetime(todas["data"])
    todas["ano"], todas["mes"] = todas["data"].dt.year, todas["data"].dt.month
    todas["periodo"] = todas["data"].dt.to_period("M")
    mensal = todas.groupby(["ceasa", "produto", "unidade", "periodo"], as_index=False)["preco"].median()
    df = todas[todas["uf"].isin(["MG", "RJ", "SP", "BR"])].drop(columns="periodo").reset_index(drop=True)
    cult = pd.read_csv(CULTURAS, sep=";", dtype=str)
    cult["ciclo_dias"] = cult["ciclo_dias"].astype(int)
    cult["janela_venda_dias"] = cult["janela_venda_dias"].astype(int)
    custos = pd.read_csv(CUSTOS, sep=";") if CUSTOS.exists() else pd.DataFrame()
    perdas = pd.read_csv(PERDAS, sep=";") if PERDAS.exists() else pd.DataFrame()
    return df, mensal, cult, pl, custos, perdas


# ----------------------------------------------------------------- séries
def _continua(s):
    """Série mensal com índice de períodos contínuo (meses sem dado ficam vazios)."""
    s = s.sort_index()
    return s.reindex(pd.period_range(s.index.min(), s.index.max(), freq="M"))


def _media_movel_12(s):
    """Média móvel centrada de 12 meses (2x12). Precisa dos 13 meses ao redor; senão fica vazio."""
    pesos = np.r_[0.5, np.ones(11), 0.5] / 12
    v = s.values.astype(float)
    out = np.full(len(v), np.nan)
    for i in range(6, len(v) - 6):
        janela = v[i - 6:i + 7]
        if not np.isnan(janela).any():
            out[i] = (janela * pesos).sum()
    return pd.Series(out, index=s.index)


def _tendencia(s):
    """Tendência de longo prazo em escala log (crescimento % constante)."""
    ok = s.dropna()
    if len(ok) < 12:
        return pd.Series(ok.mean(), index=s.index)
    t = np.array([p.ordinal for p in ok.index], dtype=float)
    a, b = np.polyfit(t, np.log(ok.values), 1)
    tt = np.array([p.ordinal for p in s.index], dtype=float)
    return pd.Series(np.exp(a * tt + b), index=s.index)


def serie_local(mensal, produto, ceasa):
    d = mensal[(mensal["produto"] == produto) & (mensal["ceasa"] == ceasa)]
    if d.empty:
        return pd.Series(dtype=float), None
    un = d["unidade"].mode().iloc[0]
    return _continua(d[d["unidade"] == un].set_index("periodo")["preco"]), un


@st.cache_data(show_spinner=False)
def modelo_produto(mensal, pl, produto):
    """Monta a base, o índice sazonal, os cenários (Q = preço ÷ tendência) e a confiança de um produto."""
    series, fonte = {}, ""
    if len(pl) and produto in set(pl["produto"]):
        p = pl[pl["produto"] == produto].copy()
        ce_pl = p["ceasa"].mode().iloc[0] if "ceasa" in p.columns else "CEASAMINAS - BELO HORIZONTE"
        p = p[p["ceasa"] == ce_pl] if "ceasa" in p.columns else p
        sigla = "BH" if "BELO HORIZONTE" in ce_pl else ce_pl.title()
        p["periodo"] = pd.PeriodIndex(p["mes"], freq="M")
        base = _continua(p.set_index("periodo")["preco"])
        bh, _ = serie_local(mensal, produto, ce_pl)
        if len(bh):
            comum = base.dropna().index.intersection(bh.dropna().index)
            k = float((bh[comum] / base[comum]).median()) if len(comum) >= 6 else 1.0
            novos = bh.dropna().index.difference(base.dropna().index)
            if len(novos):
                juntos = pd.concat([base.dropna(), bh[novos] / k]).sort_index()
                base = _continua(juntos)
        ok = base.dropna()
        fonte = f"Sua planilha de {sigla} ({ok.index.min().year}–{ok.index.max().year})"
        if ok.index.max().year > p["periodo"].max().year:
            fonte = (f"Sua planilha de {sigla} ({ok.index.min().year}–{p['periodo'].max().year}) "
                     f"+ Conab {sigla} até {ok.index.max().year}")
        series[fonte] = base
    else:
        d = mensal[(mensal["produto"] == produto) & (mensal["ceasa"] != BRASIL)]
        if len(d):
            un = d["unidade"].mode().iloc[0]
            for ce, g in d[d["unidade"] == un].groupby("ceasa"):
                s = _continua(g.set_index("periodo")["preco"])
                if s.notna().sum() >= MIN_MESES_SERIE:
                    series[ce] = s
        fonte = f"Índice combinado de {len(series)} Ceasas (Conab, {_anos_txt(series)})"
    if not series:
        return None

    razoes, Q = [], {}
    for nome, s in series.items():
        r = s / _media_movel_12(s)
        razoes.append(r.rename(nome))
        q = s / _tendencia(s)
        Q[nome] = q / q.mean()  # nivelado: em média, cenário = 1 (preço normal)
    R = pd.concat(razoes, axis=1)
    R["ano"], R["mes"] = [p.year for p in R.index], [p.month for p in R.index]
    longa = R.melt(id_vars=["ano", "mes"], var_name="serie", value_name="r").dropna()
    indice = longa.groupby("mes")["r"].median().reindex(range(1, 13))
    indice = indice / indice.mean()
    perfil = longa.groupby(["ano", "mes"])["r"].median().unstack().reindex(columns=range(1, 13))
    perfil = perfil / perfil.mean(axis=1).values[:, None]
    estab, n_comp = _estabilidade(perfil)
    Qdf = pd.concat(Q, axis=1)
    anos = sorted({p.year for p in Qdf.dropna(how="all").index})
    # Confiabilidade da época MÉDIA (Spearman-Brown): quanto mais anos, mais confiável a média
    if pd.notna(estab) and n_comp >= 2:
        r = max(estab, 0.0)
        confiab = n_comp * r / (1 + (n_comp - 1) * r) if r > 0 else 0.0
    else:
        confiab = float("nan")
    return {"fonte": fonte, "indice": indice, "perfil": perfil, "Q": Qdf, "estabilidade": estab,
            "confiabilidade": confiab, "anos_completos": n_comp,
            "anos": anos, "n_series": len(series), "series": series}


def _anos_txt(series):
    if not series:
        return "—"
    ini = min(s.dropna().index.min().year for s in series.values())
    fim = max(s.dropna().index.max().year for s in series.values())
    return f"{ini}–{fim}"


def _estabilidade(perfil):
    """Quanto o desenho da época se repete entre anos (correlação média entre anos completos)."""
    ok = perfil[perfil.notna().sum(axis=1) >= 10]
    if len(ok) < 2:
        return float("nan"), len(ok)
    c = ok.T.corr().values
    return float(np.nanmean(c[np.triu_indices(len(ok), 1)])), len(ok)


def confianca(mod):
    """Alta / Média / Baixa pela confiabilidade da época média (Spearman-Brown)."""
    c = mod["confiabilidade"]
    if pd.isna(c) or mod["anos_completos"] < 3:
        return "Baixa"
    return "Alta" if c >= 0.75 else "Média" if c >= 0.5 else "Baixa"


def esperado(R):
    """Valor esperado do cenário: média aparada (tira o maior e o menor ano quando há 5+ anos)."""
    v = np.sort(np.asarray(R, dtype=float))
    if len(v) >= 5:
        v = v[1:-1]
    return float(v.mean()) if len(v) else float("nan")


# ----------------------------------------------------------------- janela de venda e cenários
def pesos_venda(inicio, dias):
    """Quantos dias de venda caem em cada (ano, mês)."""
    pesos = {}
    for i in range(max(dias, 1)):
        d = inicio + timedelta(days=i)
        pesos[(d.year, d.month)] = pesos.get((d.year, d.month), 0) + 1
    return pesos


def meses_da_venda(inicio, dias):
    return [m for (_, m) in pesos_venda(inicio, dias)]


def _desloca(d, anos):
    try:
        return d.replace(year=d.year + anos)
    except ValueError:  # 29 de fevereiro
        return d.replace(year=d.year + anos, day=28)


def cenarios(mod, inicio, dias):
    """Para cada ano do histórico: preço real nos dias de venda ÷ tendência (mediana entre as séries).
    O ano do cenário é o ano em que a venda começa; a janela segue a sequência real de meses."""
    Q = mod["Q"]
    out = {}
    for ano in mod["anos"]:
        ini = _desloca(inicio, ano - inicio.year)
        w = pesos_venda(ini, dias)
        per = [pd.Period(year=y, month=m, freq="M") for (y, m) in w]
        if any(p not in Q.index for p in per):
            continue
        sub = Q.loc[per]
        if sub.isna().all(axis=0).all():
            continue
        pesos = np.array(list(w.values()), dtype=float)
        vals = []
        for col in sub.columns:
            v = sub[col].values
            if not np.isnan(v).any():
                vals.append(float((v * pesos).sum() / pesos.sum()))
        if vals:
            out[ano] = float(np.median(vals))
    return pd.Series(out, dtype=float)


def fator_epoca(mod, inicio, dias):
    """Índice sazonal médio dos dias de venda (só a época, sem o nível do ano)."""
    w = pesos_venda(inicio, dias)
    tot = sum(w.values())
    return sum(mod["indice"][m] * n for (_, m), n in w.items()) / tot


# ----------------------------------------------------------------- preço normal na Ceasa escolhida
def preco_normal(mensal, mod, produto, ceasa, data_venda, metodo, inflacao):
    """Preço 'normal' (sem época) na Ceasa escolhida, levado até a data da venda.
    Devolve (valor, explicação, {método: valor} para mostrar a faixa)."""
    s, _ = serie_local(mensal, produto, ceasa)
    s = s.dropna()
    if s.empty:
        return float("nan"), "sem dados nesta Ceasa", {}
    meses_ate = lambda p: (data_venda.year - p.year) * 12 + (data_venda.month - p.month)
    corr = lambda p: (1 + inflacao) ** (meses_ate(p) / 12)
    saz = mod["indice"]
    res = {}
    ult = s.iloc[-24:]
    des = ult / [saz[p.month] for p in ult.index]
    centro = ult.index[len(ult) // 2]
    res[METODOS[0]] = (float(des.mean()) * corr(centro),
                       f"média sem época de {ult.index[0].strftime('%m/%Y')} a {ult.index[-1].strftime('%m/%Y')}, "
                       f"corrigida por {inflacao:.1%} ao ano até {data_venda:%m/%Y}")
    anos_ok = s.groupby([p.year for p in s.index]).size()
    anos_ok = anos_ok[anos_ok >= 10]
    if len(anos_ok):
        a = int(anos_ok.index.max())
        res[METODOS[2]] = (float(s[[p.year == a for p in s.index]].mean()) * corr(pd.Period(year=a, month=7, freq="M")),
                           f"média de {a}, corrigida pela inflação até {data_venda:%m/%Y}")
    base = list(mod["series"].values())[0]
    if mod["n_series"] == 1 and base.notna().sum() >= 72:  # só com série longa (6+ anos)
        comum = base.dropna().index.intersection(s.index)
        if len(comum) >= 6:
            k = float((s[comum] / base[comum]).median())
            tend = _tendencia(base)
            ult_p = tend.index[-1]
            cres = (tend.iloc[-1] / tend.iloc[-13]) if len(tend) > 13 else 1.0
            val = tend.iloc[-1] * k * cres ** (meses_ate(ult_p) / 12)
            res[METODOS[1]] = (float(val), f"tendência de {base.dropna().index.min().year}–{ult_p.year} "
                                           f"({cres - 1:+.1%} ao ano), no nível desta Ceasa")
    if metodo in res:
        v, txt = res[metodo]
    else:
        v, txt = res[METODOS[0]]
        txt += " (o método escolhido precisa de pelo menos 6 anos de série; usei o recomendado)"
    return v, txt, {k: v_ for k, (v_, _) in res.items()}


# ----------------------------------------------------------------- dinheiro e estatística
def lucro_ha(preco_ceasa, desconto, prod_t_ha, perda, custo_ha):
    return preco_ceasa * (1 - desconto) * prod_t_ha * 1000 * (1 - perda) - custo_ha


def preco_empate(desconto, prod_t_ha, perda, custo_ha):
    vendavel = prod_t_ha * 1000 * (1 - perda) * (1 - desconto)
    return custo_ha / vendavel if vendavel > 0 else float("nan")


def perdas_de(perdas, produto):
    if perdas is None or perdas.empty:
        return 0.10, 0.30
    linha = perdas[perdas["produto"] == produto]
    if linha.empty:
        linha = perdas[perdas["produto"] == "PADRAO"]
    if linha.empty:
        return 0.10, 0.30
    return float(linha.iloc[0]["perda_tipica_pct"]) / 100, float(linha.iloc[0]["perda_ano_ruim_pct"]) / 100


def chance_acaso(k, n):
    """Teste do sinal: chance de 'ganhar' k ou mais de n anos por puro acaso (moeda 50/50)."""
    if n == 0:
        return float("nan")
    return sum(math.comb(n, i) for i in range(k, n + 1)) / 2 ** n


def wilson_inferior(k, n, z=1.2816):
    """Limite inferior (80%) da proporção — penaliza amostras pequenas (3 de 3 < 9 de 9)."""
    if n == 0:
        return float("nan")
    p = k / n
    den = 1 + z * z / n
    centro = p + z * z / (2 * n)
    raio = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (centro - raio) / den


def intervalo_bootstrap(x, vezes=2000, nivel=0.90, semente=42):
    x = np.asarray(x, dtype=float)
    if len(x) < 3:
        return float("nan"), float("nan")
    rng = np.random.default_rng(semente)
    medias = rng.choice(x, size=(vezes, len(x)), replace=True).mean(axis=1)
    a = (1 - nivel) / 2
    return float(np.quantile(medias, a)), float(np.quantile(medias, 1 - a))


def data_plantio(mes, hoje=None):
    """Dia 15 do próximo mês 'mes' que ainda não passou."""
    hoje = hoje or date.today()
    d = date(hoje.year, mes, 15)
    return d if d >= hoje else date(hoje.year + 1, mes, 15)


def brl(v, casas=2):
    if v is None or pd.isna(v):
        return "—"
    txt = f"R$ {v:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return txt.replace("R$ -", "−R$ ")


def pct(v):
    return "—" if pd.isna(v) else f"{v:+.0f}%".replace("+", "▲ ").replace("-", "▼ ")


def num(v, casas=1):
    return f"{v:.{casas}f}".replace(".", ",")
