"""Página "Análises avançadas": gráficos e ferramentas analíticas sobre o preço mensal de uma Ceasa."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parent))
import agro_calc as A
import modelo as M
import regiao as R
from estilo import FUNDO, TEXTO_2, cartao, visual
from modelo import MESES, brl

AZUL, VERDE, LARANJA, AMARELO = "#3987e5", "#199e70", "#d95926", "#f2c230"


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def dados():
    _, mensal, _, _, custos, perdas = M.carregar()
    return mensal, custos, perdas


mensal, custos, perdas = dados()
ceasas = sorted(mensal["ceasa"].unique())

st.title("📐 Análises avançadas")
st.markdown('<p class="dica">Gráficos e contas sobre o preço mensal. Use para entender a época, o risco e o retorno '
            "de cada produto.</p>", unsafe_allow_html=True)

c1, c2, c3 = st.columns([2, 3, 2])
produtos = sorted(mensal["produto"].unique())
produto = c1.selectbox("Produto", produtos, index=produtos.index("ALHO") if "ALHO" in produtos else 0)
ceasa_padrao = R.ceasa(R.atual())
ceasa = c2.selectbox("Ceasa", ceasas, index=ceasas.index(ceasa_padrao) if ceasa_padrao in ceasas else 0)


def serie_de(prod, cea):
    d = mensal[(mensal["produto"] == prod) & (mensal["ceasa"] == cea)].sort_values("periodo")
    return d.set_index("periodo")["preco"]


s = serie_de(produto, ceasa)
if len(s) < 24:
    st.info("Este produto e esta Ceasa têm menos de 2 anos de preço mensal. Escolha outra combinação.")
    st.stop()

tab = pd.DataFrame({"ano": s.index.year, "mes": s.index.month, "preco": s.values})
tab["media_mes"] = tab.groupby("mes")["preco"].transform("mean")
tab["desvio_pct"] = (tab["preco"] / tab["media_mes"] - 1) * 100

st.subheader("1. Mapa de calor: mês × ano")
st.markdown('<p class="dica">Verde: o preço ficou acima da média daquele mês. Vermelho: abaixo. Mostra a época do ano '
            "e como ela mudou de um ano para outro.</p>", unsafe_allow_html=True)
pv = tab.pivot(index="ano", columns="mes", values="desvio_pct").reindex(columns=range(1, 13))
fig = go.Figure(go.Heatmap(z=pv.values, x=MESES, y=pv.index.astype(str), zmid=0,
                           colorscale=[[0, LARANJA], [0.5, FUNDO], [1, VERDE]],
                           colorbar=dict(title="%", tickfont=dict(color=TEXTO_2)),
                           hovertemplate="%{y} %{x}: %{z:+.0f}%<extra></extra>"))
fig.update_yaxes(type="category")
st.plotly_chart(visual(fig, "", 360), width="stretch")

st.subheader("2. Faixa de preço por mês")
st.markdown('<p class="dica">Cada caixa mostra os preços daquele mês em todos os anos: a faixa do meio (25% a 75%), '
            "a linha é a mediana e os traços vão do menor ao maior preço. Caixas largas = mês de risco.</p>",
            unsafe_allow_html=True)
fig = go.Figure()
for m in range(1, 13):
    fig.add_trace(go.Box(y=tab.loc[tab["mes"] == m, "preco"], name=MESES[m - 1], marker_color=AZUL,
                         line=dict(color=AZUL), boxmean=False))
st.plotly_chart(visual(fig, f"R$ por {M.UNIDADES.get('KG', 'kg')}", 360, prefixo="R$ "), width="stretch")

st.subheader("3. Variação mensal (%)")
var = (s.pct_change() * 100).dropna().tail(36)
fig = go.Figure(go.Bar(x=var.index.to_timestamp(), y=var.values,
                       marker_color=[VERDE if v >= 0 else LARANJA for v in var.values],
                       hovertemplate="%{x|%b/%Y}: %{y:+.1f}%<extra></extra>"))
st.plotly_chart(visual(fig, "% sobre o mês anterior", 300, sufixo="%"), width="stretch")

st.subheader("4. Média de 12 meses com faixa")
st.markdown('<p class="dica">Linha: média dos últimos 12 meses. Faixa sombreada: entre o preço baixo (percentil 10) e o '
            "alto (percentil 90) do ano. Mostra a tendência e a variação típica.</p>", unsafe_allow_html=True)
m12 = s.rolling(12).mean()
p10 = s.rolling(12).quantile(0.1)
p90 = s.rolling(12).quantile(0.9)
x = s.index.to_timestamp()
fig = go.Figure()
fig.add_trace(go.Scatter(x=x, y=p90.values, line=dict(width=0), showlegend=False, hoverinfo="skip"))
fig.add_trace(go.Scatter(x=x, y=p10.values, fill="tonexty", fillcolor="rgba(57,135,229,0.2)", line=dict(width=0),
                         name="Faixa 10%–90%"))
fig.add_trace(go.Scatter(x=x, y=m12.values, line=dict(color=AMARELO, width=2.5), name="Média de 12 meses"))
fig.add_trace(go.Scatter(x=x, y=s.values, line=dict(color="#6b6a63", width=1), name="Preço mensal"))
st.plotly_chart(visual(fig, "R$ por kg", 340, prefixo="R$ "), width="stretch")

st.header("Ferramentas")

st.subheader("5. Comparar dois produtos (base 100)")
outro = st.selectbox("Comparar com", [p for p in produtos if p != produto],
                     index=[p for p in produtos if p != produto].index("CEBOLA") if "CEBOLA" in produtos else 0)
s2 = serie_de(outro, ceasa)
junto = pd.concat([s, s2], axis=1, join="inner").dropna()
if len(junto) >= 2:
    base = junto.iloc[0] / 100
    idx = junto / base
    fig = go.Figure()
    for col, nome, cor in [(0, produto, AZUL), (1, outro, LARANJA)]:
        fig.add_trace(go.Scatter(x=idx.index.to_timestamp(), y=idx.iloc[:, col], name=nome, line=dict(color=cor, width=2.5)))
    st.plotly_chart(visual(fig, "base 100 no primeiro mês em comum", 320), width="stretch")
    st.markdown(f'<p class="dica">No período, {produto} variou {idx.iloc[-1, 0] - 100:+.0f} pontos e {outro} '
                f"{idx.iloc[-1, 1] - 100:+.0f} pontos.</p>", unsafe_allow_html=True)
else:
    st.info("Os dois produtos não têm meses em comum nesta Ceasa.")

st.subheader("6. Ponto de equilíbrio e margem")
linha = custos[custos["produto"] == produto]
prod_padrao = float(linha["produtividade_t_ha"].iloc[0]) if len(linha) else 10.0
custo_padrao = float(linha["custo_ha_2026"].iloc[0]) if len(linha) else 100000.0
perda_padrao = M.perdas_de(perdas, produto)[0]
e1, e2, e3, e4, e5 = st.columns(5)
custo = e1.number_input("Custo total (R$/ha)", 0.0, 10_000_000.0, custo_padrao, step=1000.0)
prod_t = e2.number_input("Produtividade (t/ha)", 0.0, 1000.0, prod_padrao, step=0.5)
perda = e3.slider("Perda (%)", 0, 60, int(round(perda_padrao * 100))) / 100
desconto = e4.slider("Produtor recebe a menos (%)", 0, 50, M.DESCONTO_PADRAO) / 100
margem = e5.slider("Margem desejada (%)", 0, 100, 20) / 100
minimo = M.preco_empate(desconto, prod_t, perda, custo)
alvo = minimo * (1 + margem)
k1, k2, k3 = st.columns(3)
with k1:
    cartao("Preço mínimo na Ceasa (cobre o custo)", brl(minimo) + "/kg", "sem lucro")
with k2:
    cartao("Preço com a margem desejada", brl(alvo) + "/kg", f"margem de {margem:.0%}")
with k3:
    ultimo = float(s.iloc[-1])
    cartao("Último preço da série", brl(ultimo) + "/kg",
           "acima do alvo" if ultimo >= alvo else "abaixo do alvo", VERDE if ultimo >= alvo else LARANJA)

st.subheader("7. Risco e volatilidade")
vol = float(np.log(s).diff().std() * np.sqrt(12))
pior = float((s / s.cummax() - 1).min() * 100)
limite = st.number_input("Quero saber a chance de o preço cair abaixo de (R$/kg)", 0.0, 1000.0,
                         round(float(s.iloc[-1]) * 0.8, 2), step=0.5)
chance = float((s < limite).mean() * 100)
r1, r2, r3 = st.columns(3)
with r1:
    cartao("Volatilidade anual", f"{vol:.0%}", "quanto o preço oscila por ano")
with r2:
    cartao("Pior queda do pico", f"{pior:.0f}%", "maior queda até o próximo pico")
with r3:
    cartao("Meses abaixo do limite", f"{chance:.0f}%", f"de {len(s)} meses de histórico")

st.subheader("8. Tendência, época e ruído")
st.markdown('<p class="dica">Separa o preço em três partes: a tendência (longo prazo), o efeito da época (o que se repete '
            "todo ano) e o ruído (o que sobra, sem padrão).</p>", unsafe_allow_html=True)
trend = s.rolling(12, center=True, min_periods=6).mean()
por_mes, _ = A.indices(s)
epoca = pd.Series([por_mes.loc[p.month, "mean"] for p in s.index], index=s.index)
ruido = (s / (trend * epoca) - 1) * 100
fig = go.Figure()
fig.add_trace(go.Scatter(x=x, y=s.values, name="Preço", line=dict(color="#6b6a63", width=1)))
fig.add_trace(go.Scatter(x=x, y=trend.values, name="Tendência", line=dict(color=AMARELO, width=2.5)))
st.plotly_chart(visual(fig, "R$ por kg", 300, prefixo="R$ "), width="stretch")
fig = go.Figure(go.Bar(x=MESES, y=(por_mes["mean"].reindex(range(1, 13)) * 100 - 100).values,
                       marker_color=[VERDE if v >= 0 else LARANJA for v in (por_mes["mean"].reindex(range(1, 13)) * 100 - 100).values]))
st.plotly_chart(visual(fig, "efeito da época (%)", 240, sufixo="%"), width="stretch")
st.markdown(f'<p class="dica">Ruído: o preço fica em média {ruido.abs().mean():.0f}% longe do que a tendência e a época '
            "explicam.</p>", unsafe_allow_html=True)
