"""Painel "Preço Seguro" — preços de hortifrúti nas Ceasas de MG, RJ e SP.

Como abrir (dentro da pasta do projeto):
    .venv\\Scripts\\streamlit.exe run painel\\app.py
Depois abra http://localhost:8501 no Chrome.
"""
import sqlite3
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import sys
sys.path.append(str(Path(__file__).resolve().parent))
from modelo import BANCO, BRASIL, ceagesp_diario, media_brasil  # BANCO: banco local ou, online, o montado dos dados públicos

# Cores (paleta validada para fundo escuro e daltonismo) — uma cor fixa por ano
CORES_ANOS = {2019: "#008300", 2020: "#9085e9", 2021: "#e66767",
              2022: "#3987e5", 2023: "#d95926", 2024: "#199e70", 2025: "#c98500", 2026: "#d55181"}
CINZAS_ANOS = {2017: ("#8a897f", "dash"), 2018: ("#6b6a63", "dot")}  # anos antigos: cinza + tracejado
FUNDO = "#1a1a19"
TEXTO = "#f0efec"
TEXTO_2 = "#c3c2b7"
GRADE = "#2e2e2b"
MESES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
UNIDADES = {"KG": "kg", "DZ": "dúzia", "UN": "unidade", "MC": "maço", "CX": "caixa", "SC": "saco"}

st.set_page_config(page_title="Preço Seguro", page_icon="🌱", layout="wide")

st.markdown(
    """
    <style>
      .block-container {padding-top: 2rem; max-width: 1200px;}
      .cartao {background:#1f1f1d; border:1px solid #2e2e2b; border-radius:14px; padding:16px 18px; height:100%;}
      .cartao .rotulo {color:#c3c2b7; font-size:0.85rem; margin-bottom:4px;}
      .cartao .valor {color:#f0efec; font-size:1.7rem; font-weight:650; line-height:1.2;}
      .cartao .detalhe {color:#9a998f; font-size:0.8rem; margin-top:4px;}
      .sobe {color:#e66767;} .desce {color:#4cc38a;}
      .dica {color:#c3c2b7; font-size:0.9rem; margin:-6px 0 6px 0;}
      h1, h2, h3 {letter-spacing:-0.01em;}
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data
def carregar():
    with sqlite3.connect(BANCO) as con:
        df = pd.read_sql("SELECT uf, ceasa, produto, unidade, data, preco FROM precos WHERE uf IN ('MG','RJ','SP')", con)
        br = media_brasil(con)
        df = pd.concat([df, br.drop(columns="n_ceasas")], ignore_index=True)
    df["data"] = pd.to_datetime(df["data"])
    df["ano"] = df["data"].dt.year
    df["mes"] = df["data"].dt.month
    return df


@st.cache_data
def ceasas_por_dia(produto):
    """Quantas Ceasas entram, em média, na média do Brasil de um produto (por dia)."""
    with sqlite3.connect(BANCO) as con:
        b = media_brasil(con)
        total = pd.read_sql("SELECT COUNT(DISTINCT ceasa) FROM precos WHERE produto = ?", con, params=(produto,)).iloc[0, 0]
    b = b[b["produto"] == produto]
    return (b["n_ceasas"].mean() if len(b) else 0), int(total)


@st.cache_data
def mensal_extra(produto, ceasa):
    """Médias mensais de fontes mais novas (R$/kg), uma por mês: CeasaMinas > boletins Ceagesp > boletim Conab."""
    partes = []
    with sqlite3.connect(BANCO) as con:
        if con.execute("SELECT name FROM sqlite_master WHERE name='precos_mensal'").fetchone():
            pm = pd.read_sql("SELECT mes, preco, fonte FROM precos_mensal WHERE produto = ? AND ceasa = ?", con,
                             params=(produto, ceasa))
            partes.append(pm.assign(ordem=pm["fonte"].str.startswith("Conab") * 2))
        if ceasa == "CEAGESP - SAO PAULO":
            cg = ceagesp_diario(con)
            cg = cg[cg["produto"] == produto] if len(cg) else cg
            if len(cg):
                partes.append(cg.assign(mes=cg["data"].str[:7]).groupby("mes", as_index=False)["preco"].mean()
                              .assign(fonte="boletins da Ceagesp", ordem=1))
    if not partes:
        return pd.DataFrame(columns=["ano", "mes", "preco", "fonte"])
    d = pd.concat(partes).sort_values("ordem").drop_duplicates("mes")
    return pd.DataFrame({"ano": d["mes"].str[:4].astype(int), "mes": d["mes"].str[5:7].astype(int),
                         "preco": d["preco"], "fonte": d["fonte"]})


def brl(v):
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def cartao(rotulo, valor, detalhe="", classe=""):
    st.markdown(
        f'<div class="cartao"><div class="rotulo">{rotulo}</div>'
        f'<div class="valor {classe}">{valor}</div><div class="detalhe">{detalhe}</div></div>',
        unsafe_allow_html=True,
    )


def estilo(fig, titulo_y):
    fig.update_layout(
        paper_bgcolor=FUNDO, plot_bgcolor=FUNDO, font=dict(color=TEXTO, size=13),
        margin=dict(l=10, r=10, t=10, b=10), height=420, hovermode="x unified",
        legend=dict(orientation="h", y=1.08, x=0, font=dict(color=TEXTO_2)),
        hoverlabel=dict(bgcolor="#262624", font_color=TEXTO),
    )
    fig.update_xaxes(showgrid=False, linecolor=GRADE, tickfont=dict(color=TEXTO_2))
    fig.update_yaxes(gridcolor=GRADE, zeroline=False, tickfont=dict(color=TEXTO_2),
                     title=dict(text=titulo_y, font=dict(color=TEXTO_2)), tickprefix="R$ ")
    return fig


if not BANCO.exists():
    st.error("Banco de dados não encontrado. Rode primeiro: coleta\\preparar_dados.py")
    st.stop()

df = carregar()

# ---------- Cabeçalho ----------
st.title("🌱 Preço Seguro")
st.markdown(
    "Acompanhe o **preço no atacado** de frutas e hortaliças nas Ceasas de **Minas Gerais, Rio de Janeiro e São Paulo** "
    "e compare como ele se comporta em cada época do ano."
)

# ---------- Filtros ----------
c1, c2, c3 = st.columns([1, 1, 2])
produtos = sorted(df["produto"].unique())
produto = c1.selectbox("Produto", produtos, index=produtos.index("TOMATE") if "TOMATE" in produtos else 0)
uf = c2.selectbox("Estado", ["MG", "RJ", "SP", "BR"], index=2,
                  format_func=lambda u: "Brasil (média de todas as Ceasas)" if u == "BR" else u)
ceasas = sorted(df.loc[(df["uf"] == uf) & (df["produto"] == produto), "ceasa"].unique())
if not ceasas:
    st.warning("Este produto não tem preços neste estado. Escolha outro produto ou estado.")
    st.stop()
padrao = next((i for i, c in enumerate(ceasas) if "SAO PAULO" in c or "BELO HORIZONTE" in c or "RIO DE JANEIRO" in c), 0)
ceasa = c3.selectbox("Ceasa", ceasas, index=padrao)

dados = df[(df["produto"] == produto) & (df["ceasa"] == ceasa)].sort_values("data")
if ceasa == BRASIL:
    media_dia, total_ceasas = ceasas_por_dia(produto)
    st.info(
        f"🇧🇷 **Média do Brasil:** em cada dia, é a média dos preços de todas as Ceasas que informaram preço de "
        f"{produto.title()} naquele dia — em média {media_dia:.0f} de {total_ceasas} Ceasas do país. "
        "Só entram os dias com pelo menos 5 Ceasas informando. Como as Ceasas que informam mudam de um dia "
        "para o outro, a média do dia pode oscilar um pouco mais."
    )
unidade = UNIDADES.get(dados["unidade"].iloc[0], dados["unidade"].iloc[0].lower())

# ---------- Cartões de resumo ----------
ultimo = dados.iloc[-1]
ha_30 = dados[dados["data"] <= ultimo["data"] - pd.Timedelta(days=30)]
meses_por_ano = dados.groupby("ano")["mes"].nunique()
anos_cheios = meses_por_ano[meses_por_ano >= 10]
ano_ult = int(anos_cheios.index.max()) if len(anos_cheios) else int(ultimo["ano"])  # último ano com 10+ meses
do_ano = dados[dados["ano"] == ano_ult]

k1, k2, k3, k4 = st.columns(4)
with k1:
    cartao("Último preço registrado", brl(ultimo["preco"]), f"por {unidade} · {ultimo['data']:%d/%m/%Y}")
with k2:
    if len(ha_30):
        ref = ha_30.iloc[-1]["preco"]
        var = (ultimo["preco"] / ref - 1) * 100
        seta = "▲" if var > 0 else "▼" if var < 0 else "■"
        classe = "sobe" if var > 0 else "desce" if var < 0 else ""
        cartao("Variação em 30 dias", f"{seta} {abs(var):.1f}%".replace(".", ","), f"antes: {brl(ref)}", classe)
    else:
        cartao("Variação em 30 dias", "—", "sem dados suficientes")
with k3:
    cartao(f"Preço médio em {ano_ult}", brl(do_ano["preco"].mean()), f"{len(do_ano)} dias com preço")
with k4:
    cartao(f"Menor e maior em {ano_ult}", f"{brl(do_ano['preco'].min())} – {brl(do_ano['preco'].max())}".replace("R$ ", ""),
           "R$ por " + unidade)

st.write("")

# ---------- Gráfico 1: comparação entre anos ----------
st.subheader("📅 Comparação entre anos")
st.markdown(
    f'<p class="dica">Cada linha é um ano. O eixo de baixo mostra os meses e o da esquerda o preço médio do mês (R$ por {unidade}). '
    "Linhas que sobem nos mesmos meses mostram um padrão de época (sazonalidade).</p>",
    unsafe_allow_html=True,
)
mensal = dados.groupby(["ano", "mes"], as_index=False).agg(preco=("preco", "mean"), n=("preco", "size"))
mensal = mensal[mensal["n"] >= 5][["ano", "mes", "preco"]]  # mês com menos de 5 dias de preço não é média confiável
fonte_anos = "Conab / Prohort (preço mais comum do dia, média do mês)"
if ceasa == "CEASAMINAS - BELO HORIZONTE":
    with sqlite3.connect(BANCO) as con:
        tem_pl = con.execute("SELECT name FROM sqlite_master WHERE name='planilha_bh'").fetchone()
        cols = [r[1] for r in con.execute("PRAGMA table_info(planilha_bh)")] if tem_pl else []
        if "relativo" in cols:  # versão online: a planilha está só como desenho (sem R$), então o gráfico usa a Conab
            pl = pd.DataFrame()
        elif tem_pl and "ceasa" in cols:
            pl = pd.read_sql("SELECT mes, preco FROM planilha_bh WHERE produto = ? AND ceasa = ?", con, params=(produto, ceasa))
        elif tem_pl:
            pl = pd.read_sql("SELECT mes, preco FROM planilha_bh WHERE produto = ?", con, params=(produto,))
        else:
            pl = pd.DataFrame()
    if len(pl):
        pl["ano"], pl["mes"] = pl["mes"].str[:4].astype(int), pl["mes"].str[5:].astype(int)
        mensal = pl[["ano", "mes", "preco"]]
        fonte_anos = "sua planilha de séries históricas de BH (2017 em diante)"
if dados["unidade"].iloc[0] == "KG":  # as fontes mensais novas são em R$/kg
    extra = mensal_extra(produto, ceasa)
    cm = extra[extra["fonte"].str.startswith("CeasaMinas")]
    if len(cm) and fonte_anos.startswith("Conab"):  # Conab mede outro preço: a CeasaMinas vale para todos os anos que ela cobre
        mensal = mensal[mensal["ano"] < cm["ano"].min()]
    ult = (mensal["ano"] * 100 + mensal["mes"]).max() if len(mensal) else 0
    extra = extra[extra["ano"] * 100 + extra["mes"] > ult]  # só os meses depois do último que já existe
    if len(extra):
        novas = " e ".join(dict.fromkeys(extra["fonte"]))
        p = extra.sort_values(["ano", "mes"]).iloc[0]
        fonte_anos = f"{fonte_anos}; a partir de {MESES[p['mes'] - 1].lower()}/{p['ano']}: {novas}" if len(mensal) else novas
        mensal = pd.concat([mensal, extra[["ano", "mes", "preco"]]], ignore_index=True)
ano_atual = pd.Timestamp.today().year
mensal = mensal[(mensal.groupby("ano")["mes"].transform("count") >= 2) | (mensal["ano"] == ano_atual)]  # ano em curso entra mesmo com 1 mês
fig = go.Figure()
for ano, g in mensal.sort_values(["ano", "mes"]).groupby("ano"):
    cor, traco = CINZAS_ANOS.get(ano, (CORES_ANOS.get(ano, "#9085e9"), "solid"))
    nome = f"{ano} (parcial, até {MESES[g['mes'].max() - 1].lower()})" if ano == ano_atual and len(g) < 12 else str(ano)
    fig.add_trace(go.Scatter(
        x=[MESES[m - 1] for m in g["mes"]], y=g["preco"], name=nome, mode="lines+markers",
        line=dict(color=cor, width=2.5, dash=traco),
        marker=dict(size=8, line=dict(color=FUNDO, width=2)),
        hovertemplate=f"{ano}: R$ %{{y:.2f}}<extra></extra>",
    ))
fig.update_xaxes(categoryorder="array", categoryarray=MESES)
st.plotly_chart(estilo(fig, f"R$ por {unidade}"), width="stretch")
st.caption(f"Dados deste gráfico: {fonte_anos}. Dica: clique num ano na legenda para esconder ou mostrar a linha.")

with st.expander("Ver os números deste gráfico"):
    tabela = mensal.pivot(index="mes", columns="ano", values="preco").round(2)
    tabela.index = [MESES[m - 1] for m in tabela.index]
    st.dataframe(tabela, width="stretch")

# ---------- Gráfico 2: histórico completo ----------
st.subheader("📈 Histórico completo")
st.markdown(
    '<p class="dica">Os pontos claros são os preços de cada dia. A linha azul é a média de 4 semanas, '
    "que suaviza os sobe-e-desce do dia a dia e mostra a tendência.</p>",
    unsafe_allow_html=True,
)
serie = dados.set_index("data")["preco"]
media = serie.rolling("28D").mean()
fig2 = go.Figure()
fig2.add_trace(go.Scatter(x=serie.index, y=serie.values, name="Preço do dia", mode="markers",
                          marker=dict(size=4, color="#6b6a63"), hovertemplate="Dia: R$ %{y:.2f}<extra></extra>"))
fig2.add_trace(go.Scatter(x=media.index, y=media.values, name="Média de 4 semanas", mode="lines",
                          line=dict(color="#3987e5", width=2.5), hovertemplate="Média: R$ %{y:.2f}<extra></extra>"))
st.plotly_chart(estilo(fig2, f"R$ por {unidade}"), width="stretch")

# ---------- Gráfico 3: comparação entre Ceasas ----------
st.subheader("🏙️ Comparação entre Ceasas")
st.markdown(
    f'<p class="dica">O mesmo produto ({produto.title()}) em Ceasas diferentes, mês a mês. '
    "Ajuda a ver onde o preço está melhor e se as regiões sobem e descem juntas. Escolha até 4 Ceasas.</p>",
    unsafe_allow_html=True,
)
do_produto = df[df["produto"] == produto]
un_principal = do_produto["unidade"].mode().iloc[0]
do_produto = do_produto[do_produto["unidade"] == un_principal]
todas = sorted(do_produto["ceasa"].unique())
principais = [c for c in ["CEASAMINAS - BELO HORIZONTE", "CEASA/RJ - RIO DE JANEIRO", "CEAGESP - SAO PAULO", BRASIL] if c in todas]
escolhidas = st.multiselect("Ceasas para comparar", todas, default=principais, max_selections=4)

CORES_FIXAS = {"CEASAMINAS - BELO HORIZONTE": "#3987e5", "CEASA/RJ - RIO DE JANEIRO": "#d95926",
               "CEAGESP - SAO PAULO": "#199e70", BRASIL: "#9085e9"}
EXTRAS = ["#c98500", "#d55181", "#e66767", "#008300"]
if escolhidas:
    comp = do_produto[do_produto["ceasa"].isin(escolhidas)].copy()
    comp["mes_ref"] = comp["data"].dt.to_period("M").dt.to_timestamp()
    comp = comp.groupby(["ceasa", "mes_ref"], as_index=False)["preco"].mean()
    fig3 = go.Figure()
    extra = iter(EXTRAS)
    for nome in escolhidas:
        g = comp[comp["ceasa"] == nome]
        cor = CORES_FIXAS.get(nome) or next(extra)
        fig3.add_trace(go.Scatter(
            x=g["mes_ref"], y=g["preco"], name=nome.title(), mode="lines+markers",
            line=dict(color=cor, width=2.5), marker=dict(size=7, line=dict(color=FUNDO, width=2)),
            hovertemplate=f"{nome.title()}: R$ %{{y:.2f}}<extra></extra>",
        ))
    un_txt = UNIDADES.get(un_principal, un_principal.lower())
    st.plotly_chart(estilo(fig3, f"R$ por {un_txt}"), width="stretch")

    resumo = (do_produto[do_produto["ceasa"].isin(escolhidas)]
              .assign(ano=lambda d: d["data"].dt.year)
              .pivot_table(index="ceasa", columns="ano", values="preco", aggfunc="mean").round(2))
    resumo.index = [i.title() for i in resumo.index]
    with st.expander("Ver o preço médio de cada ano por Ceasa"):
        st.dataframe(resumo, width="stretch")
else:
    st.info("Escolha pelo menos uma Ceasa para ver a comparação.")

# ---------- Gráfico 4: boletins da Ceagesp (2026) ----------
@st.cache_data(ttl=3600)
def carregar_ceagesp():
    with sqlite3.connect(BANCO) as con:
        tem = con.execute("SELECT name FROM sqlite_master WHERE name='ceagesp'").fetchone()
        if not tem:
            return pd.DataFrame()
        d = pd.read_sql("SELECT * FROM ceagesp", con)
    d["data"] = pd.to_datetime(d["data"])
    return d


cg = carregar_ceagesp()
if not cg.empty:
    st.subheader("🧾 Ceagesp São Paulo — boletins de 2026")
    st.markdown(
        '<p class="dica">Preços dos boletins oficiais da Ceagesp (segunda, quarta e sexta). A faixa sombreada vai do '
        "<b>menor</b> ao <b>maior</b> preço do dia; a linha é o preço <b>mais comum</b>. "
        "Atenção: aqui os produtos são separados por tipo e classificação, por isso os valores não se comparam "
        "direto com os gráficos acima.</p>",
        unsafe_allow_html=True,
    )
    b1, b2 = st.columns([2, 1])
    nomes = sorted(cg["produto"].unique())
    sugestao = next((i for i, n in enumerate(nomes) if n.startswith(produto.split()[0])), 0)
    prod_cg = b1.selectbox("Produto (Ceagesp)", nomes, index=sugestao)
    classes = sorted(cg.loc[cg["produto"] == prod_cg, "classificacao"].unique())
    classe_cg = b2.selectbox("Tipo / classificação", classes)
    s = cg[(cg["produto"] == prod_cg) & (cg["classificacao"] == classe_cg)].sort_values("data")
    un_cg = UNIDADES.get(s["unidade"].iloc[0], s["unidade"].iloc[0].lower())
    fig4 = go.Figure()
    fig4.add_trace(go.Scatter(x=s["data"], y=s["preco_max"], mode="lines", line=dict(width=0),
                              showlegend=False, hovertemplate="Maior: R$ %{y:.2f}<extra></extra>"))
    fig4.add_trace(go.Scatter(x=s["data"], y=s["preco_min"], mode="lines", line=dict(width=0), fill="tonexty",
                              fillcolor="rgba(57,135,229,0.18)", name="Faixa menor–maior",
                              hovertemplate="Menor: R$ %{y:.2f}<extra></extra>"))
    fig4.add_trace(go.Scatter(x=s["data"], y=s["preco_comum"], mode="lines+markers", name="Mais comum",
                              line=dict(color="#3987e5", width=2.5), marker=dict(size=6),
                              hovertemplate="Comum: R$ %{y:.2f}<extra></extra>"))
    st.plotly_chart(estilo(fig4, f"R$ por {un_cg}"), width="stretch")

# ---------- Rodapé ----------
st.divider()
st.caption(
    "Fontes: Ceagesp (boletins de 2026) e Conab / Prohort (preço mais comum do dia no atacado), com dados de "
    f"{df['data'].min():%d/%m/%Y} a {df['data'].max():%d/%m/%Y}. "
    "Versão de teste — os preços podem ter dias faltando e não são recomendação de compra ou venda."
)
