"""Página "Confiabilidade": prova de acerto no passado, fontes e conferências dos dados."""
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parent))
import modelo as M
from modelo import MESES, brl, num

FUNDO, TEXTO, TEXTO_2, GRADE = "#1a1a19", "#f0efec", "#c3c2b7", "#2e2e2b"
AZUL, LARANJA = "#3987e5", "#d95926"

st.markdown(
    """
    <style>
      .block-container {padding-top: 2rem; max-width: 1200px;}
      .cartao {background:#1f1f1d; border:1px solid #2e2e2b; border-radius:14px; padding:16px 18px; height:100%;}
      .cartao .rotulo {color:#c3c2b7; font-size:0.85rem;}
      .cartao .valor {color:#f0efec; font-size:1.45rem; font-weight:650; line-height:1.25;}
      .cartao .detalhe {color:#9a998f; font-size:0.8rem; margin-top:4px;}
      .dica {color:#c3c2b7; font-size:0.92rem;}
      .aviso {background:#2a2418; border:1px solid #5c4a1f; border-radius:12px; padding:12px 16px; color:#e8dcc0; font-size:0.88rem;}
    </style>
    """,
    unsafe_allow_html=True,
)


def cartao(rotulo, valor, detalhe="", cor=None):
    estilo = f' style="color:{cor}"' if cor else ""
    st.markdown(f'<div class="cartao"><div class="rotulo">{rotulo}</div><div class="valor"{estilo}>{valor}</div>'
                f'<div class="detalhe">{detalhe}</div></div>', unsafe_allow_html=True)


def visual(fig, titulo_y, altura=340, sufixo=""):
    fig.update_layout(paper_bgcolor=FUNDO, plot_bgcolor=FUNDO, font=dict(color=TEXTO, size=13), height=altura,
                      margin=dict(l=10, r=10, t=30, b=10), hovermode="x unified",
                      legend=dict(orientation="h", y=1.12, x=0, font=dict(color=TEXTO_2)),
                      hoverlabel=dict(bgcolor="#262624", font_color=TEXTO))
    fig.update_xaxes(showgrid=False, linecolor=GRADE, tickfont=dict(color=TEXTO_2), type="category")
    fig.update_yaxes(gridcolor=GRADE, zeroline=False, tickfont=dict(color=TEXTO_2), ticksuffix=sufixo,
                     title=dict(text=titulo_y, font=dict(color=TEXTO_2)))
    return fig


@st.cache_data(show_spinner="Testando o modelo nos anos passados…")
def prova_passado(_mod, produto, n_top=3, min_treino=3):
    """Para cada ano Y: escolhe os n_top meses mais caros usando SÓ os anos antes de Y; mede o ganho real em Y."""
    s = list(_mod["series"].values())
    linhas = []
    razoes = []
    for serie in s:
        r = serie / M._media_movel_12(serie)
        razoes.append(pd.DataFrame({"ano": [p.year for p in r.index], "mes": [p.month for p in r.index], "r": r.values,
                                    "preco": serie.values}).dropna(subset=["preco"]))
    tudo = pd.concat(razoes)
    anos = sorted(tudo["ano"].unique())
    for ano in anos:
        treino = tudo[(tudo["ano"] < ano)].dropna(subset=["r"])
        if treino["ano"].nunique() < min_treino:
            continue
        idx = treino.groupby("mes")["r"].median()
        if len(idx) < 12:
            continue
        top = list(idx.sort_values(ascending=False).head(n_top).index)
        real = tudo[tudo["ano"] == ano].groupby("mes")["preco"].median()
        if len(real) < 12:
            continue
        ganho = real[top].mean() / real.mean() - 1
        top_real = list(real.sort_values(ascending=False).head(n_top).index)
        acertos = len(set(top) & set(real.sort_values(ascending=False).head(6).index))
        linhas.append({"ano": ano, "anos_treino": treino["ano"].nunique(), "previstos": top, "mais_caros": top_real,
                       "ganho": ganho, "acertos_top6": acertos})
    return pd.DataFrame(linhas)


df, mensal, cult, pl, custos, perdas = M.carregar()

st.title("✅ Dá para confiar?")
st.markdown(
    "Esta página existe para **provar** — ou não — que o sistema funciona. Aqui você vê: **(1)** se o modelo teria "
    "acertado nos anos passados, **(2)** quanto o produtor recebe de fato a menos que a Ceasa, **(3)** de onde vem cada "
    "número e **(4)** o que já foi conferido nos dados. Sem esconder os pontos fracos."
)

# ---------- 1. Prova no passado ----------
st.subheader("1. Se você tivesse seguido o modelo nos anos passados, teria vendido melhor?")
st.markdown(
    '<p class="dica">Teste <b>sem trapaça</b>: para cada ano, o modelo escolhe os <b>3 meses mais caros usando só os anos '
    "anteriores</b> — exatamente o que você teria em mãos naquela época. Depois comparamos com o que realmente aconteceu "
    "naquele ano: quanto o preço desses 3 meses ficou acima da média do ano. <b>0% = o mesmo que vender em qualquer mês.</b></p>",
    unsafe_allow_html=True,
)
nomes = dict(zip(cult["nome"], cult["produto"]))
opcoes = [n for n in ["Cenoura", "Alho", "Cebola"] if n in nomes] + [n for n in nomes if n not in ("Cenoura", "Alho", "Cebola")]
nome = st.selectbox("Cultura", opcoes)
mod = M.modelo_produto(mensal, pl, nomes[nome])
bt = prova_passado(mod, nomes[nome]) if mod else pd.DataFrame()
if bt.empty:
    st.warning(
        f"**{nome}: ainda não dá para fazer este teste.** São precisos pelo menos 3 anos completos antes do ano testado, "
        f"e a base desta cultura ({mod['fonte'] if mod else 'sem dados'}) ainda é curta. Este é exatamente o motivo da "
        "confiança baixa — mais anos de dados resolvem."
    )
else:
    k = int((bt["ganho"] > 0).sum())
    n = len(bt)
    if n < 3:
        st.warning(f"**Atenção: só {n} ano(s) testável(is) para {nome}.** Isso não prova nada — pode ter sido sorte. "
                   "Precisamos de mais anos de dados para esta cultura.")
    g1, g2, g3, g4 = st.columns(4)
    with g1:
        cartao("Anos testados", f"{n}", f"{bt['ano'].min()} a {bt['ano'].max()} · base: {mod['fonte']}")
    with g2:
        cartao("Vendeu acima da média do ano", f"{k} de {n} anos", f"chance de ser só sorte: {M.chance_acaso(k, n):.0%}",
               "#4cc38a" if k > n / 2 else "#e66767")
    with g3:
        cartao("Ganho médio no preço", f"{bt['ganho'].mean():+.0%}".replace(".", ","),
               f"mediana {bt['ganho'].median():+.0%} · pior ano {bt['ganho'].min():+.0%}")
    with g4:
        cartao("Meses certos", f"{bt['acertos_top6'].mean():.1f} de 3".replace(".", ","),
               "dos 3 meses previstos, quantos estavam entre os 6 mais caros do ano")
    fig = go.Figure(go.Bar(
        x=[str(a) for a in bt["ano"]], y=bt["ganho"] * 100, marker=dict(color=[AZUL if v > 0 else LARANJA for v in bt["ganho"]]),
        text=[f"{v:+.0%}" for v in bt["ganho"]], textposition="outside",
        hovertemplate="%{x}: vendeu %{y:+.0f}% vs média do ano<extra></extra>"))
    fig.add_hline(y=0, line=dict(color="#8a897f", width=1))
    st.plotly_chart(visual(fig, "preço dos meses previstos vs média do ano", sufixo="%"), width="stretch")
    tb = pd.DataFrame({
        "Ano testado": bt["ano"], "Anos usados para prever": bt["anos_treino"],
        "Meses que o modelo indicaria": bt["previstos"].map(lambda v: ", ".join(MESES[x - 1] for x in v)),
        "3 meses mais caros de verdade": bt["mais_caros"].map(lambda v: ", ".join(MESES[x - 1] for x in v)),
        "Ganho real": bt["ganho"].map(lambda v: f"{v:+.0%}"),
    })
    st.dataframe(tb, hide_index=True, width="stretch")
    st.caption("O teste mede só o PREÇO (época). Não inclui custo, perdas nem o risco de muitos produtores plantarem juntos.")

# ---------- 2. Diferença Ceasa -> produtor ----------
st.subheader("2. Quanto o produtor recebe de fato a menos que a Ceasa?")
with sqlite3.connect(M.BANCO) as con:
    tem = con.execute("SELECT name FROM sqlite_master WHERE name='preco_produtor'").fetchone()
    pp = pd.read_sql("SELECT * FROM preco_produtor WHERE nivel LIKE 'PREÇO RECEBIDO%'", con) if tem else pd.DataFrame()
if pp.empty:
    st.info("Dados de preço ao produtor ainda não importados (coleta\\importar_conab_arquivo.py).")
else:
    al = pp[(pp["produto"] == "ALHO") & (pp["uf"] == "MG")].groupby("mes")["preco_kg"].mean()
    bh = df[(df["produto"] == "ALHO") & (df["ceasa"] == "CEASAMINAS - BELO HORIZONTE")].copy()
    bh["m"] = bh["data"].dt.strftime("%Y-%m")
    bh = bh.groupby("m")["preco"].mean()
    comum = al.index.intersection(bh.index)
    dif = 1 - al[comum] / bh[comum]
    st.markdown(
        '<p class="dica">Comparação oficial da Conab para o <b>alho em Minas Gerais</b>: preço que o <b>produtor recebeu</b> '
        "× preço na <b>CeasaMinas BH</b>, mês a mês. É o caso em que as duas fontes são comparáveis (mesmo produto e região).</p>",
        unsafe_allow_html=True,
    )
    d1, d2, d3 = st.columns(3)
    with d1:
        cartao("Diferença típica (mediana)", f"{dif.median():.0%}", f"{len(dif)} meses de 2025 · alho MG")
    with d2:
        cartao("Faixa mês a mês", f"{dif.min():.0%} a {dif.max():.0%}", "varia com a época e a classificação")
    with d3:
        cartao("Valor usado no sistema", f"{M.DESCONTO_PADRAO}%", "dentro do medido e do que o produtor relata (10% a 20%)")
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(x=list(comum), y=bh[comum].values, name="CeasaMinas BH", mode="lines+markers",
                              line=dict(color=AZUL, width=2.5), hovertemplate="Ceasa: R$ %{y:.2f}<extra></extra>"))
    fig2.add_trace(go.Scatter(x=list(comum), y=al[comum].values, name="Produtor (MG)", mode="lines+markers",
                              line=dict(color=LARANJA, width=2.5), hovertemplate="Produtor: R$ %{y:.2f}<extra></extra>"))
    st.plotly_chart(visual(fig2, "R$ por kg", altura=300), width="stretch")
    ult = al.sort_index().tail(1)
    st.markdown(f'<div class="aviso">📉 <b>Alerta de 2026:</b> o alho em MG foi pago ao produtor a <b>{brl(ult.iloc[0])}/kg</b> em '
                f"{ult.index[0][5:]}/{ult.index[0][:4]} — contra {brl(al.max())}/kg no pico de 2025. A base de preços da Ceasa no "
                "sistema vai até dez/2025; por isso, no alho, a realidade de 2026 tende a ser <b>pior</b> do que a análise mostra.</div>",
                unsafe_allow_html=True)

# ---------- 3. Fontes ----------
st.subheader("3. De onde vem cada número")
with sqlite3.connect(M.BANCO) as con:
    def periodo(sql):
        try:
            a, b = con.execute(sql).fetchone()
            return f"{a} a {b}" if a else "—"
        except Exception:
            return "—"
    fontes = pd.DataFrame([
        {"Fonte": "Conab / Prohort — preços diários das Ceasas", "O que usamos": "preço mais comum do dia, 43 Ceasas, 48 produtos",
         "Período no sistema": periodo("SELECT min(data), max(data) FROM precos"),
         "Situação": "⚠️ link oficial fora do ar desde out/2026; usamos a cópia do Internet Archive de 02/01/2026",
         "Link": "gov.br/conab → Hortigranjeiros (Prohort)"},
        {"Fonte": "Sua planilha de séries históricas (BH)", "O que usamos": "preço médio mensal de alho, cenoura e cebola",
         "Período no sistema": periodo("SELECT min(mes), max(mes) FROM planilha_bh"),
         "Situação": "✅ conferida: anda junto com a CeasaMinas BH (correlação 0,98–0,99)", "Link": "arquivo do produtor"},
        {"Fonte": "Ceagesp — boletins de cotação (São Paulo)", "O que usamos": "menor, mais comum e maior preço por tipo",
         "Período no sistema": periodo("SELECT min(data), max(data) FROM ceagesp"),
         "Situação": "✅ coletado direto do site oficial", "Link": "ceagesp.gov.br/cotacoes"},
        {"Fonte": "Conab — preço recebido pelo produtor (por estado)", "O que usamos": "diferença Ceasa → produtor; preço de 2026",
         "Período no sistema": periodo("SELECT min(mes), max(mes) FROM preco_produtor"),
         "Situação": "✅ arquivo oficial (cópia do Internet Archive de 28/02/2026)", "Link": "portaldeinformacoes.conab.gov.br"},
        {"Fonte": "Conab — custos de produção", "O que usamos": "custo por hectare de tomate, batata, inhame, batata-doce, quiabo, mandioca",
         "Período no sistema": "2018 a 2023, corrigidos pela inflação", "Situação": "✅ oficial (corrigido = estimativa)",
         "Link": "portaldeinformacoes.conab.gov.br"},
        {"Fonte": "Custos de alho, cenoura e cebola", "O que usamos": "custo por hectare 2026",
         "Período no sistema": "2026", "Situação": "Produtor + ANAPA (ago/2026) + CNA/Campo Futuro + Cepea + Epagri", "Link": "ver 💰 Custos"},
        {"Fonte": "Ciclo, época de plantio e perdas", "O que usamos": "datas de plantio, colheita e perdas por cultura",
         "Período no sistema": "—", "Situação": "⚠️ estimativas de calendários públicos — conferir com agrônomo",
         "Link": "dados\\culturas.csv e dados\\perdas.csv"},
    ])
st.dataframe(fontes, hide_index=True, width="stretch")

# ---------- 4. Conferências ----------
st.subheader("4. O que já foi conferido nos dados")
st.markdown(
    """
- ✅ **Sem registros repetidos** (mesma Ceasa, produto e dia) e **sem preço zero ou vazio**.
- ✅ **Unidades consistentes:** cada produto usa sempre a mesma unidade (kg, dúzia ou unidade) em todas as Ceasas.
- ✅ **Valores fora do padrão:** só 0,02% dos preços diários; o modelo usa a **mediana** do mês, que não se deixa levar por eles.
- ✅ **Planilha de BH:** confere com a Conab (mesmo sobe-e-desce); o nível é 8–16% diferente, mas o modelo usa só a **variação**.
- ✅ **Auditoria independente** do modelo (14 pontos analisados) — os erros encontrados foram corrigidos na versão 2.
- ✅ **Teste justo** nas comparações: o ano testado nunca é usado para escolher os meses.
- ⚠️ **Pouco histórico** para a maioria das culturas (Conab só de jun/2022 a dez/2025) → **confiança baixa** marcada em vermelho.
- ⚠️ **O modelo não prevê choques novos:** geada, seca, excesso de área plantada no país, mudança de câmbio.
"""
)
st.caption("Para rodar a conferência completa dos dados: .venv\\Scripts\\python.exe coleta\\validar_dados.py")
