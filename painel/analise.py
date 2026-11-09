"""Página: Modelo Preditivo Sazonal (v2) — análise detalhada de uma cultura."""
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parent))
import modelo as M
from modelo import MESES, MESES_LONGO, UNIDADES, brl, num, pct

FUNDO, TEXTO, TEXTO_2, GRADE = "#1a1a19", "#f0efec", "#c3c2b7", "#2e2e2b"
AZUL, LARANJA, CINZA = "#3987e5", "#d95926", "#6b6a63"
COR_CONF = {"Alta": "#4cc38a", "Média": "#e0b341", "Baixa": "#e66767"}

st.markdown(
    """
    <style>
      .block-container {padding-top: 2rem; max-width: 1200px;}
      .cartao {background:#1f1f1d; border:1px solid #2e2e2b; border-radius:14px; padding:16px 18px; height:100%;}
      .cartao .rotulo {color:#c3c2b7; font-size:0.85rem;}
      .cartao .valor {color:#f0efec; font-size:1.45rem; font-weight:650; line-height:1.25;}
      .cartao .detalhe {color:#9a998f; font-size:0.8rem; margin-top:4px;}
      .dica {color:#c3c2b7; font-size:0.92rem;}
      .passo {background:#1f1f1d; border-left:3px solid #3987e5; border-radius:8px; padding:10px 14px; margin:6px 0; color:#e6e5e0;}
      .aviso {background:#2a2418; border:1px solid #5c4a1f; border-radius:12px; padding:12px 16px; color:#e8dcc0; font-size:0.88rem;}
      .selo {display:inline-block; padding:2px 10px; border-radius:999px; font-weight:600; font-size:0.85rem;}
    </style>
    """,
    unsafe_allow_html=True,
)


def cartao(rotulo, valor, detalhe="", cor=None):
    estilo = f' style="color:{cor}"' if cor else ""
    st.markdown(f'<div class="cartao"><div class="rotulo">{rotulo}</div><div class="valor"{estilo}>{valor}</div>'
                f'<div class="detalhe">{detalhe}</div></div>', unsafe_allow_html=True)


def visual(fig, titulo_y, altura=400, sufixo="", prefixo=""):
    fig.update_layout(paper_bgcolor=FUNDO, plot_bgcolor=FUNDO, font=dict(color=TEXTO, size=13), height=altura,
                      margin=dict(l=10, r=10, t=30, b=10), hovermode="x unified",
                      legend=dict(orientation="h", y=1.12, x=0, font=dict(color=TEXTO_2)),
                      hoverlabel=dict(bgcolor="#262624", font_color=TEXTO))
    fig.update_xaxes(showgrid=False, linecolor=GRADE, tickfont=dict(color=TEXTO_2))
    fig.update_yaxes(gridcolor=GRADE, zeroline=False, tickfont=dict(color=TEXTO_2), ticksuffix=sufixo,
                     tickprefix=prefixo, title=dict(text=titulo_y, font=dict(color=TEXTO_2)))
    return fig


def mil(v):
    """R$ curto para rótulos de barra: 12,3 mil / −1,2 mil."""
    if pd.isna(v):
        return ""
    return ("−" if v < 0 else "") + f"{abs(v) / 1000:.1f} mil".replace(".", ",")


df, mensal, cult, pl, custos, perdas = M.carregar()
hoje = date.today()

# ---------- Cabeçalho ----------
st.title(f"🔬 {M.NOME_MODELO}")
st.caption(f"Versão {M.VERSAO} · análise detalhada de uma cultura")
st.markdown(
    "Em que mês plantar para vender na melhor época, quanto o preço costuma variar, qual o risco e quanto pode "
    "sobrar por hectare depois da **diferença Ceasa → produtor**, das **perdas** e da **queda de produtividade fora da época**."
)

# ---------- Escolhas ----------
nomes = dict(zip(cult["nome"], cult["produto"]))
c1, c2 = st.columns([2, 3])
nome = c1.selectbox("Cultura", list(nomes), index=list(nomes).index("Cenoura"))
produto = nomes[nome]
regiao = c2.selectbox("Sua região", list(M.REGIOES))
cal_col, ceasa_padrao = M.REGIOES[regiao]
c3, c4 = st.columns([3, 2])
ceasas = sorted(df["ceasa"].unique())
ceasa = c3.selectbox("Ceasa de referência para o preço", ceasas, index=ceasas.index(ceasa_padrao))
onde = "na média do Brasil (todas as Ceasas)" if ceasa == M.BRASIL else f"na {ceasa.title()}"
metodo = c4.selectbox("Como estimar o preço normal", M.METODOS)

linha = cult[cult["produto"] == produto].iloc[0]
calendario = linha[cal_col]
cs = custos[custos["produto"] == produto] if len(custos) else pd.DataFrame()
perda_tip_pad, perda_ruim_pad = M.perdas_de(perdas, produto)
_, unidade_cod = M.serie_local(mensal, produto, ceasa)
unidade_cod = unidade_cod or "KG"
unidade = UNIDADES.get(unidade_cod, unidade_cod.lower())

with st.expander("⚙️ Custos, perdas, produtividade e inflação — ajuste para a sua realidade", expanded=True):
    e1, e2, e3 = st.columns(3)
    custo_ha = e1.number_input("Custo de produção (R$ por hectare)", 0, 2_000_000,
                               int(cs.iloc[0]["custo_ha_2026"]) if len(cs) else 0, step=5000,
                               help="Deixe 0 se não souber: a página mostra só a análise de preço.")
    prod_t = e2.number_input("Produtividade na boa época (t/ha)", 0.0, 300.0,
                             float(cs.iloc[0]["produtividade_t_ha"]) if len(cs) else 0.0, step=0.5)
    desconto = e3.slider("O produtor recebe quanto a menos que a Ceasa (%)", 0, 50, M.DESCONTO_PADRAO,
                         help="Frete, comissão, embalagem e margem do atacadista. Normalmente 10% a 20%, às vezes mais.") / 100
    e4, e5, e6, e7 = st.columns(4)
    perda_tip = e4.slider("Perda típica (%)", 0, 70, int(perda_tip_pad * 100),
                          help="Parte da colheita que não vira venda: quebra, descarte, classificação.") / 100
    perda_ruim = e5.slider("Perda num ano ruim (%)", 0, 90, int(perda_ruim_pad * 100),
                           help="Ex.: no alho, a quebra já passou de 50% em alguns casos.") / 100
    queda = e6.slider("Queda de produtividade fora da época (%)", 0, 80, M.QUEDA_FORA_EPOCA,
                      help="Plantar fora da época costuma render menos (clima, doenças). 20% é uma estimativa inicial.") / 100
    inflacao = e7.slider("Inflação esperada (% ao ano)", 0.0, 15.0, M.INFLACAO_PADRAO, step=0.5,
                         help="Usada só para levar o preço normal de hoje até a data da venda.") / 100
tem_custo = custo_ha > 0 and prod_t > 0 and unidade_cod == "KG"
if custo_ha > 0 and unidade_cod != "KG":
    st.info(f"Esta cultura é vendida por {unidade}: o lucro por hectare precisa de preço por kg e foi desligado.")

mod = M.modelo_produto(mensal, pl, produto)
if mod is None:
    st.warning("Ainda não há histórico suficiente para esta cultura.")
    st.stop()
conf = M.confianca(mod)

# ---------- Cálculo dos 12 meses de plantio ----------
linhas = []
for mes in range(1, 13):
    plantio = M.data_plantio(mes, hoje)
    ciclo, janela = M.ciclo_janela(linha, plantio)  # verão/inverno conforme o mês do plantio
    colheita = plantio + timedelta(days=ciclo)
    meio = colheita + timedelta(days=janela // 2)
    R = M.cenarios(mod, colheita, janela)
    pn, pn_txt, faixa = M.preco_normal(mensal, mod, produto, ceasa, meio, metodo, inflacao)
    boa = calendario[mes - 1] == "1"
    prod_ef = prod_t * (1 if boa else 1 - queda)
    E = M.esperado(R)
    r = {"mes": mes, "plantio": plantio, "colheita": colheita, "ciclo": ciclo, "janela": janela, "meses_v": M.meses_da_venda(colheita, janela),
         "R": R, "E": E, "epoca": M.fator_epoca(mod, colheita, janela), "boa": boa, "prod_ef": prod_ef,
         "pn": pn, "pn_txt": pn_txt, "faixa": faixa, "atacado": pn * E, "produtor": pn * E * (1 - desconto),
         "k_acima": int((R > 1).sum()), "n": len(R)}
    if tem_custo and len(R):
        anos_l = M.lucro_ha(pn * R, desconto, prod_ef, perda_tip, custo_ha)
        r.update(lucro=M.lucro_ha(pn * E, desconto, prod_ef, perda_tip, custo_ha), lucro_anos=anos_l,
                 lucro_ruim=M.lucro_ha(pn * R.min(), desconto, prod_ef, perda_ruim, custo_ha),
                 lucro_bom=float(anos_l.max()), k_lucro=int((anos_l > 0).sum()))
    linhas.append(r)
tab = pd.DataFrame(linhas)
tab = tab[tab["n"] > 0].reset_index(drop=True)
if tab.empty:
    st.warning("O histórico não cobre os meses de venda desta cultura.")
    st.stop()
chave = "lucro" if tem_custo else "E"
boas = tab[tab["boa"]]
ordem = (boas if len(boas) else tab).sort_values(chave, ascending=False)
melhor = ordem.iloc[0]
top3 = set(ordem.head(3)["mes"])

# ---------- 1. Resumo ----------
st.subheader("1. Resumo")
anos_txt = f"{mod['anos'][0]}–{mod['anos'][-1]}"
st.markdown(
    f'<p class="dica">Base do histórico: <b>{mod["fonte"]}</b> · cenários de {len(melhor["R"])} anos ({anos_txt}) · '
    f"{M.texto_ciclo(linha)} · preço em R$ por {unidade} {onde}. "
    f'Confiança na época: <span class="selo" style="background:{COR_CONF[conf]}22;color:{COR_CONF[conf]}">{conf}</span></p>',
    unsafe_allow_html=True,
)
if conf == "Baixa":
    st.warning(
        f"**Confiança baixa:** com {mod['anos_completos']} anos completos de histórico, o desenho da época "
        f"(meses caros × baratos) ainda não se repete de forma confiável. Use os resultados com cautela — "
        "mais anos de dados (ex.: uma planilha como a de BH) deixam a análise muito mais segura."
    )
k1, k2, k3, k4 = st.columns(4)
with k1:
    cartao("Melhor mês para plantar", MESES_LONGO[melhor["mes"] - 1].capitalize(),
           ("✅ boa época na sua região" if melhor["boa"] else "⚠️ fora da época na sua região") +
           f" · plantio em {melhor['plantio']:%d/%m/%Y}")
with k2:
    cartao("Venda prevista", " · ".join(MESES[x - 1] for x in melhor["meses_v"]),
           f"colheita a partir de {melhor['colheita']:%d/%m/%Y}")
with k3:
    cartao("Preço esperado ao produtor", brl(melhor["produtor"]),
           f"por {unidade} · na Ceasa {brl(melhor['atacado'])} ({pct((melhor['E'] - 1) * 100)} vs preço normal)")
with k4:
    if tem_custo:
        cartao("Lucro esperado por hectare", brl(melhor["lucro"], 0),
               f"lucro em {melhor['k_lucro']} de {melhor['n']} anos · ano ruim: {brl(melhor['lucro_ruim'], 0)}",
               "#4cc38a" if melhor["lucro"] >= 0 else "#e66767")
    else:
        cartao("Preço acima do normal", f"{melhor['k_acima']} de {melhor['n']} anos",
               "informe custo e produtividade para ver o lucro")
faixa = melhor["faixa"]
if len(faixa) > 1:
    st.caption("Preço normal pelos métodos disponíveis: " +
               " · ".join(f"{k.split(' (')[0]}: {brl(v)}/{unidade}" for k, v in faixa.items()) +
               ". A diferença entre eles mostra quanto a escolha do preço base pesa no resultado.")
if tem_custo and tab["lucro"].max() < 0:
    st.error(
        f"⚠️ Com os valores atuais, **todos os meses de plantio dão prejuízo** no cenário esperado. O \"melhor mês\" é só o de "
        f"**menor prejuízo**. Para empatar, o preço na Ceasa precisaria chegar a "
        f"{brl(M.preco_empate(desconto, melhor['prod_ef'], perda_tip, custo_ha))}/{unidade}."
    )

# ---------- 2. Os 12 meses de plantio ----------
st.subheader("2. Em que mês plantar? Os 12 meses comparados")
if tem_custo:
    st.markdown(
        '<p class="dica">Cada barra é um mês de plantio. A altura é o <b>lucro esperado por hectare</b>. O traço fino vai '
        "do <b>ano ruim</b> (pior ano do histórico + perda de ano ruim) até o <b>melhor ano</b>. Azul: boa época na sua "
        f"região; cinza: fora da época (já com {queda:.0%} a menos de produtividade).</p>",
        unsafe_allow_html=True,
    )
    y, y_ruim, y_bom = tab["lucro"], tab["lucro_ruim"], tab["lucro_bom"]
    titulo, fmt, pref, suf = "Lucro por hectare", "R$ %{y:,.0f}", "R$ ", ""
else:
    st.markdown(
        '<p class="dica">Cada barra é um mês de plantio: quanto o preço na venda costuma ficar <b>acima ou abaixo do '
        "preço normal</b>. O traço fino vai do pior ao melhor ano do histórico.</p>",
        unsafe_allow_html=True,
    )
    y = (tab["E"] - 1) * 100
    y_ruim = tab["R"].map(lambda s: (s.min() - 1) * 100)
    y_bom = tab["R"].map(lambda s: (s.max() - 1) * 100)
    titulo, fmt, pref, suf = "acima / abaixo do preço normal", "%{y:+.0f}%", "", "%"
fig = go.Figure()
for boa, cor, nome_leg in [(True, AZUL, "Boa época na sua região"), (False, CINZA, "Fora da época")]:
    sel = tab["boa"] == boa
    if not sel.any():
        continue
    fig.add_trace(go.Bar(
        x=[MESES[i - 1] for i in tab.loc[sel, "mes"]], y=y[sel], name=nome_leg, marker=dict(color=cor),
        error_y=dict(type="data", symmetric=False, array=(y_bom - y)[sel], arrayminus=(y - y_ruim)[sel],
                     color="#9a998f", thickness=1.2, width=4),
        text=["★" if mm in top3 else "" for mm in tab.loc[sel, "mes"]], textposition="outside",
        hovertemplate=f"Plantio em %{{x}}: {fmt}<extra></extra>",
    ))
fig.add_hline(y=0, line=dict(color="#8a897f", width=1))
fig.update_xaxes(categoryorder="array", categoryarray=MESES, title=dict(text="mês do plantio", font=dict(color=TEXTO_2)))
st.plotly_chart(visual(fig, titulo, sufixo=suf, prefixo=pref), width="stretch")
st.caption("★ = os 3 melhores meses dentro da boa época. Passe o mouse nas barras para ver os valores.")

tabela = pd.DataFrame({
    "Plantio": [f"{MESES[r - 1]} ({p:%d/%m/%Y})" for r, p in zip(tab["mes"], tab["plantio"])],
    "Época na região": tab["boa"].map({True: "✅ Boa", False: "⚠️ Fora"}),
    "Colheita a partir de": tab["colheita"].map(lambda d: f"{d:%d/%m/%Y}"),
    "Venda em": tab["meses_v"].map(lambda v: " · ".join(MESES[x - 1] for x in v)),
    "Só a época": ((tab["epoca"] - 1) * 100).map(pct),
    "Esperado (época + anos)": ((tab["E"] - 1) * 100).map(pct),
    "Anos acima do normal": [f"{k} de {n}" for k, n in zip(tab["k_acima"], tab["n"])],
    f"Preço na Ceasa (R$/{unidade})": tab["atacado"].map(brl),
    f"Preço ao produtor (R$/{unidade})": tab["produtor"].map(brl),
})
if tem_custo:
    tabela["Produtividade (t/ha)"] = tab["prod_ef"].map(lambda v: num(v))
    tabela["Lucro esperado/ha"] = tab["lucro"].map(lambda v: brl(v, 0))
    tabela["Ano ruim/ha"] = tab["lucro_ruim"].map(lambda v: brl(v, 0))
    tabela["Melhor ano/ha"] = tab["lucro_bom"].map(lambda v: brl(v, 0))
    tabela["Anos com lucro"] = [f"{k} de {n}" for k, n in zip(tab["k_lucro"], tab["n"])]
with st.expander("Ver a tabela completa dos 12 meses de plantio"):
    st.dataframe(tabela, hide_index=True, width="stretch")
    st.caption("\"Só a época\" = efeito dos meses de venda num ano normal. \"Esperado\" = média dos anos do histórico "
               "(tirando o melhor e o pior quando há 5 anos ou mais), que inclui também se o ano foi caro ou barato.")

# ---------- 3. Comportamento do preço no ano ----------
st.subheader("3. Como o preço se comporta ao longo do ano")
st.markdown(
    '<p class="dica">A linha é a <b>época</b>: quanto cada mês costuma ficar acima ou abaixo da média dos 12 meses ao redor '
    "(0% = normal). Medir contra a média móvel tira a inflação e a tendência. A faixa vai do <b>pior ao melhor ano</b>.</p>",
    unsafe_allow_html=True,
)
perfil = mod["perfil"]
fig2 = go.Figure()
fig2.add_trace(go.Scatter(x=MESES, y=(perfil.max() - 1) * 100, mode="lines", line=dict(width=0), showlegend=False,
                          hovertemplate="Melhor ano: %{y:+.0f}%<extra></extra>"))
fig2.add_trace(go.Scatter(x=MESES, y=(perfil.min() - 1) * 100, mode="lines", line=dict(width=0), fill="tonexty",
                          fillcolor="rgba(57,135,229,0.18)", name="Do pior ao melhor ano",
                          hovertemplate="Pior ano: %{y:+.0f}%<extra></extra>"))
fig2.add_trace(go.Scatter(x=MESES, y=(mod["indice"].values - 1) * 100, mode="lines+markers", name="Época (mediana)",
                          line=dict(color=AZUL, width=2.5), marker=dict(size=8, line=dict(color=FUNDO, width=2)),
                          hovertemplate="Época: %{y:+.0f}%<extra></extra>"))
fig2.add_hline(y=0, line=dict(color="#8a897f", width=1, dash="dot"))
st.plotly_chart(visual(fig2, "acima / abaixo do normal", sufixo="%"), width="stretch")

chance_mes = (perfil > 1).sum() / perfil.notna().sum() * 100
fig2b = go.Figure(go.Bar(x=MESES, y=chance_mes.values, marker=dict(color=AZUL),
                         text=[f"{v:.0f}%" for v in chance_mes.values], textposition="outside",
                         hovertemplate="%{x}: acima do normal em %{y:.0f}% dos anos<extra></extra>"))
fig2b.add_hline(y=50, line=dict(color="#8a897f", width=1, dash="dot"))
st.markdown('<p class="dica"><b>Em quantos anos cada mês ficou acima do normal</b> (linha pontilhada = 50%).</p>',
            unsafe_allow_html=True)
st.plotly_chart(visual(fig2b, "% dos anos", altura=270, sufixo="%"), width="stretch")

# ---------- 4. Mapa de calor ----------
st.subheader("4. Mapa de calor: cada ano, mês a mês")
st.markdown(
    '<p class="dica">Cada quadrado é um mês de um ano, comparado com a média dos 12 meses ao redor. <b>Azul</b> = acima; '
    "<b>laranja</b> = abaixo; cinza = perto do normal. Colunas com a mesma cor em quase todos os anos = época firme.</p>",
    unsafe_allow_html=True,
)
z = (perfil - 1) * 100
lim = float(np.nanmax(np.abs(z.values))) if np.isfinite(np.nanmax(np.abs(z.values))) else 50
fig3 = go.Figure(go.Heatmap(
    z=z.values, x=MESES, y=[str(a) for a in z.index], zmid=0, zmin=-lim, zmax=lim,
    colorscale=[[0, LARANJA], [0.5, "#3a3a37"], [1, AZUL]], xgap=2, ygap=2,
    text=[[("" if pd.isna(v) else f"{v:+.0f}%") for v in row] for row in z.values], texttemplate="%{text}",
    textfont=dict(size=11, color=TEXTO), colorbar=dict(ticksuffix="%", tickfont=dict(color=TEXTO_2)),
    hovertemplate="%{y} · %{x}: %{z:+.0f}% vs normal<extra></extra>",
))
fig3.update_layout(hovermode="closest")
fig3.update_yaxes(type="category")
st.plotly_chart(visual(fig3, "", altura=max(260, 34 * len(z) + 80)), width="stretch")
st.caption(f"Repetição da época entre anos: correlação média {num(mod['estabilidade'], 2)} · "
           f"confiabilidade da média de {mod['anos_completos']} anos: {num(mod['confiabilidade'], 2)} (0 a 1) → confiança {conf}.")

# ---------- 5. Cenários de risco ----------
st.subheader("5. Cenários de risco para um mês de plantio")
op = [f"{MESES_LONGO[r - 1].capitalize()} ({p:%d/%m/%Y})" for r, p in zip(tab["mes"], tab["plantio"])]
esc = st.selectbox("Mês de plantio para analisar", op, index=int(tab.index[tab["mes"] == melhor["mes"]][0]))
r = tab.iloc[op.index(esc)]
if tem_custo:
    st.markdown('<p class="dica">Lucro por hectare no cenário esperado, combinando a <b>diferença Ceasa → produtor</b> '
                "(linhas) com as <b>perdas</b> (colunas).</p>", unsafe_allow_html=True)
    descs = sorted({0.10, desconto, 0.25})
    perds = sorted({0.0, perda_tip, perda_ruim})
    grade = pd.DataFrame(
        [[brl(M.lucro_ha(r["atacado"], d, r["prod_ef"], p, custo_ha), 0) for p in perds] for d in descs],
        index=[f"Produtor recebe {d:.0%} a menos" for d in descs], columns=[f"Perda de {p:.0%}" for p in perds])
    st.dataframe(grade, width="stretch")
    st.markdown('<p class="dica"><b>E se o preço repetir cada ano do histórico?</b> Cada barra é o lucro por hectare se a '
                "época <b>e</b> o nível daquele ano se repetirem (com a perda típica).</p>", unsafe_allow_html=True)
    la = r["lucro_anos"]
    fig4 = go.Figure(go.Bar(
        x=[str(a) for a in la.index], y=la.values, marker=dict(color=[AZUL if v >= 0 else LARANJA for v in la.values]),
        text=[mil(v) for v in la.values], textposition="outside", hovertemplate="Como em %{x}: R$ %{y:,.0f}/ha<extra></extra>"))
    fig4.add_hline(y=0, line=dict(color="#8a897f", width=1))
    fig4.update_xaxes(type="category")
    st.plotly_chart(visual(fig4, "Lucro por hectare", altura=320, prefixo="R$ "), width="stretch")
    q1, q2, q3 = st.columns(3)
    with q1:
        cartao("Anos com lucro", f"{r['k_lucro']} de {r['n']}",
               f"chance de isso ser só acaso: {M.chance_acaso(r['k_lucro'], r['n']):.0%}" if r["k_lucro"] > r["n"] / 2 else "")
    with q2:
        cartao("Preço mínimo na Ceasa para empatar", f"{brl(M.preco_empate(desconto, r['prod_ef'], perda_tip, custo_ha))}/{unidade}",
               f"com perda típica · esperado: {brl(r['atacado'])}")
    with q3:
        cartao("Preço mínimo num ano de perda ruim", f"{brl(M.preco_empate(desconto, r['prod_ef'], perda_ruim, custo_ha))}/{unidade}",
               f"com perda de {perda_ruim:.0%}")
else:
    st.info("Informe o custo de produção e a produtividade no quadro ⚙️ acima para ver os cenários de lucro e risco.")

# ---------- 6. Passo a passo ----------
st.subheader("6. Passo a passo do cálculo (mês escolhido acima)")
passos = [
    f"<b>Plantio</b> em {r['plantio']:%d/%m/%Y} + ciclo de {r['ciclo']} dias (para plantio neste mês) = <b>colheita a partir de {r['colheita']:%d/%m/%Y}</b>; "
    f"colheita/venda por cerca de {r['janela']} dias em <b>{', '.join(MESES_LONGO[x - 1] for x in r['meses_v'])}</b> "
    "(cada mês pesa pelos dias de venda que caem nele).",
    f"<b>Preço normal</b> {onde}: <b>{brl(r['pn'])}/{unidade}</b> ({r['pn_txt']}).",
    f"<b>Época</b> dos meses de venda: {pct((r['epoca'] - 1) * 100)} num ano normal. "
    f"<b>Histórico</b> ({len(r['R'])} anos, época + nível do ano): de {pct((r['R'].min() - 1) * 100)} a {pct((r['R'].max() - 1) * 100)}; "
    f"<b>esperado {pct((r['E'] - 1) * 100)}</b> (média sem o melhor e o pior ano).",
    f"<b>Preço esperado na Ceasa</b> = {brl(r['pn'])} × {num(r['E'], 2)} = <b>{brl(r['atacado'])}/{unidade}</b>.",
    f"<b>Preço ao produtor</b> = {brl(r['atacado'])} × (1 − {desconto:.0%}) = <b>{brl(r['produtor'])}/{unidade}</b>.",
]
if tem_custo:
    vend = r["prod_ef"] * (1 - perda_tip)
    extra = "" if r["boa"] else f" (já com {queda:.0%} a menos por ser fora da época)"
    passos += [
        f"<b>Produção vendável</b> = {num(r['prod_ef'])} t/ha{extra} × (1 − {perda_tip:.0%} de perda) = <b>{num(vend)} t/ha</b>.",
        f"<b>Receita</b> = {brl(r['produtor'])} × {f'{vend * 1000:,.0f}'.replace(',', '.')} kg = <b>{brl(r['produtor'] * vend * 1000, 0)}/ha</b>.",
        f"<b>Lucro esperado</b> = receita − custo de {brl(custo_ha, 0)} = <b>{brl(r['lucro'], 0)}/ha</b>.",
    ]
for i, p in enumerate(passos, 1):
    st.markdown(f'<div class="passo">{i}. {p}</div>', unsafe_allow_html=True)

# ---------- 7. Ano todo x melhores meses ----------
st.subheader("7. Plantar o ano todo × plantar só nos melhores meses")
st.markdown(
    '<p class="dica">Duas estratégias para a mesma área: <b>A) Ano todo</b> (área dividida nos 12 meses de plantio) e '
    "<b>B) Melhores meses</b> (só nos meses que vendem melhor). Comparamos ano a ano: se a época <b>e</b> o nível de "
    "cada ano do histórico se repetirem, quanto cada estratégia rende? Os meses fora da época já entram com "
    f"{queda:.0%} a menos de produtividade.</p>",
    unsafe_allow_html=True,
)
s1, s2 = st.columns(2)
n_meses = s1.slider("Quantos meses de plantio na estratégia B", 1, 6, 3)
area = s2.number_input("Sua área total (hectares)", 0.5, 100000.0, 10.0, step=0.5) if tem_custo else None
if tem_custo:
    V = pd.DataFrame({int(x["mes"]): x["lucro_anos"] for _, x in tab.iterrows()})
    fmt_v, rotulo_v = (lambda v: brl(v, 0)), "Lucro por hectare"
else:
    V = pd.DataFrame({int(x["mes"]): (x["R"] - 1) * 100 for _, x in tab.iterrows()})
    fmt_v, rotulo_v = pct, "Preço vs normal"
V = V.dropna(how="all")
boa_mes = dict(zip(tab["mes"], tab["boa"]))
candidatos = [mm for mm in V.columns if boa_mes[mm]]
if len(candidatos) < n_meses:
    candidatos = list(V.columns)
estr_a = V.mean(axis=1)
escolhidos = list(V[candidatos].mean().sort_values(ascending=False).head(n_meses).index)
estr_b_vista = V[escolhidos].mean(axis=1)
estr_b, contagem = {}, {}
for ano in V.index:
    esc_ano = list(V.drop(index=ano)[candidatos].mean().sort_values(ascending=False).head(n_meses).index)
    estr_b[ano] = V.loc[ano, esc_ano].mean()
    for mm in esc_ano:
        contagem[mm] = contagem.get(mm, 0) + 1
estr_b = pd.Series(estr_b).dropna()
estr_a = estr_a.reindex(estr_b.index)

if len(estr_b) < 3:
    st.warning("São precisos pelo menos 3 anos de histórico para esta comparação.")
else:
    dif = estr_b - estr_a
    n_d, k_b = len(dif), int((dif > 0).sum())
    lo, hi = M.intervalo_bootstrap(dif.values)
    sem_ext = dif.drop(index=dif.abs().idxmax()).mean()
    # teste dos dois lados: chance de QUALQUER uma das estratégias ganhar tantos anos por acaso
    p_acaso = min(1.0, 2 * M.chance_acaso(max(k_b, n_d - k_b), n_d))
    if n_d < 5:
        veredito, cor_v = "Inconclusivo: poucos anos de histórico", "#e0b341"
    elif lo > 0:
        veredito, cor_v = "B é melhor — diferença consistente", "#4cc38a"
    elif hi < 0:
        veredito, cor_v = "A é melhor — diferença consistente", "#4cc38a"
    else:
        veredito, cor_v = "Sem diferença clara entre A e B", "#e0b341"
    st.markdown(f'<p class="dica">Meses escolhidos para B: <b>{", ".join(MESES_LONGO[mm - 1] for mm in escolhidos)}</b>. '
                f'Veredito: <span class="selo" style="background:{cor_v}22;color:{cor_v}">{veredito}</span></p>',
                unsafe_allow_html=True)
    v1, v2, v3 = st.columns(3)
    with v1:
        cartao("A) Ano todo — média por ano", fmt_v(estr_a.mean()), f"pior ano {fmt_v(estr_a.min())} · melhor {fmt_v(estr_a.max())}")
    with v2:
        cartao("B) Melhores meses — média (teste justo)", fmt_v(estr_b.mean()), f"pior ano {fmt_v(estr_b.min())} · melhor {fmt_v(estr_b.max())}")
    with v3:
        txt_area = f"na sua área de {area:g} ha: {brl(dif.mean() * area, 0)} por ano · " if tem_custo else ""
        cartao("Diferença B − A", (f"{brl(dif.mean(), 0)}/ha" if tem_custo else f"{dif.mean():+.0f} pontos"),
               f"{txt_area}B foi melhor em {k_b} de {n_d} anos", "#4cc38a" if dif.mean() >= 0 else "#e66767")

    fig7 = go.Figure()
    fig7.add_trace(go.Bar(x=[str(a) for a in estr_a.index], y=estr_a.values, name="A) Ano todo", marker=dict(color=LARANJA),
                          text=[mil(v) if tem_custo else f"{v:+.0f}%" for v in estr_a.values], textposition="outside",
                          hovertemplate="A em %{x}: %{y:,.0f}<extra></extra>"))
    fig7.add_trace(go.Bar(x=[str(a) for a in estr_b.index], y=estr_b.values, name="B) Melhores meses (teste justo)",
                          marker=dict(color=AZUL), text=[mil(v) if tem_custo else f"{v:+.0f}%" for v in estr_b.values],
                          textposition="outside", hovertemplate="B em %{x}: %{y:,.0f}<extra></extra>"))
    fig7.add_hline(y=0, line=dict(color="#8a897f", width=1))
    fig7.update_layout(barmode="group", bargap=0.25, bargroupgap=0.08)
    fig7.update_xaxes(type="category")
    st.plotly_chart(visual(fig7, rotulo_v, altura=360, prefixo="R$ " if tem_custo else "", sufixo="" if tem_custo else "%"),
                    width="stretch")
    st.caption("Os números em cima das barras ajudam a ver anos com valor pequeno (ex.: anos de preço muito baixo).")

    def linha_resumo(s):
        return {"Média por ano": fmt_v(s.mean()), "Mediana": fmt_v(s.median()), "Pior ano": fmt_v(s.min()),
                "Melhor ano": fmt_v(s.max()), "Anos positivos": f"{int((s > 0).sum())} de {len(s)}",
                "Oscilação (desvio padrão)": (brl(s.std(), 0) if tem_custo else f"{s.std():.0f} pontos")}
    st.dataframe(pd.DataFrame({"A) Ano todo": linha_resumo(estr_a), "B) Teste justo": linha_resumo(estr_b),
                               "B) Olhando todos os anos": linha_resumo(estr_b_vista.reindex(estr_b.index)),
                               "Diferença B − A": linha_resumo(dif)}), width="stretch")
    u = (lambda v: brl(v, 0)) if tem_custo else (lambda v: f"{v:+.0f} pontos")
    st.markdown(
        f"""
**O quanto dá para confiar na diferença:**
- Intervalo de confiança de 90% da diferença média: **{u(lo)} a {u(hi)}** {"(com menos de 5 anos, este intervalo não é confiável)" if n_d < 5 else "(não cruza o zero → diferença consistente)" if lo > 0 or hi < 0 else "(cruza o zero → pode ser acaso)"}.
- Chance de uma estratégia ganhar {max(k_b, n_d - k_b)} de {n_d} anos **por puro acaso**: **{p_acaso:.0%}** (abaixo de 10% é um bom sinal).
- Sem o ano mais extremo ({dif.abs().idxmax()}), a diferença média seria **{u(sem_ext)}**.
"""
    )
    with st.expander("ℹ️ O que é o \"teste justo\""):
        vezes = ", ".join(f"{MESES[mm - 1]} ({n}×)" for mm, n in sorted(contagem.items(), key=lambda x: -x[1]))
        st.markdown(
            f"""
- **Olhando todos os anos:** os meses de B são escolhidos com o histórico inteiro, inclusive o ano testado — como escolher o cavalo depois da corrida.
- **Teste justo:** para cada ano, os meses de B são escolhidos **só com os outros anos**, como se aquele ano ainda não tivesse acontecido.
- Meses que mais vezes entraram em B no teste justo: {vezes}.
"""
        )
    st.markdown(
        f"""
**O que os números não mostram:**
- **Ano todo:** renda o ano inteiro, uso contínuo de máquinas e mão de obra, risco espalhado. A queda de produtividade fora da época está em **{queda:.0%}** — ajuste no quadro ⚙️ se na sua região for diferente.
- **Melhores meses:** pede mais capital e mão de obra de uma vez e deixa a área parada no resto do ano. Se muitos produtores fizerem o mesmo, a oferta nesses meses sobe e o preço pode cair — o histórico não prevê isso.
"""
    )

st.markdown(
    f'<div class="aviso">⚠️ <b>Como ler este resultado.</b> O {M.NOME_MODELO} usa o que <b>aconteceu</b> nos anos do histórico '
    "para estimar o que <b>costuma</b> acontecer. Ele não prevê choques novos (geada, seca, excesso de área no país). "
    "Ciclo, época de plantio, perdas, produtividade, inflação e a diferença Ceasa → produtor são <b>estimativas</b> que você "
    "pode ajustar no quadro ⚙️. Use como apoio à decisão, junto com a orientação de um agrônomo.</div>",
    unsafe_allow_html=True,
)
