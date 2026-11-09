"""Página "O que plantar agora": ranking de culturas pela época de venda prevista (Modelo Preditivo Sazonal v2)."""
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parent))
import modelo as M
from modelo import MESES, UNIDADES, brl, pct

FUNDO, TEXTO, TEXTO_2, GRADE = "#1a1a19", "#f0efec", "#c3c2b7", "#2e2e2b"
CORES = ["#3987e5", "#d95926", "#199e70"]
SELO = {"Alta": "🟢 Alta", "Média": "🟡 Média", "Baixa": "🔴 Baixa"}

st.markdown(
    """
    <style>
      .block-container {padding-top: 2rem; max-width: 1200px;}
      .cartao {background:#1f1f1d; border:1px solid #2e2e2b; border-radius:14px; padding:16px 18px; margin-bottom:10px;}
      .cartao .rotulo {color:#c3c2b7; font-size:0.85rem;}
      .cartao .valor {color:#f0efec; font-size:1.5rem; font-weight:650; line-height:1.25;}
      .cartao .detalhe {color:#9a998f; font-size:0.8rem; margin-top:4px;}
      .dica {color:#c3c2b7; font-size:0.9rem;}
      .aviso {background:#2a2418; border:1px solid #5c4a1f; border-radius:12px; padding:12px 16px; color:#e8dcc0; font-size:0.88rem;}
    </style>
    """,
    unsafe_allow_html=True,
)

df, mensal, cult, pl, custos, perdas = M.carregar()

# ---------- Cabeçalho ----------
st.title("🌱 O que plantar agora")
st.caption(f"Cálculos do {M.NOME_MODELO} (versão {M.VERSAO}). Para ver uma cultura em detalhes, use 🔬 Análise por cultura.")
st.markdown(
    "Escolha **onde você está** e **quando vai plantar**. O sistema calcula quando cada cultura estará pronta para venda e "
    "mostra, pelo histórico de preços, **quais costumam valer mais nessa época** — e **o quanto dá para confiar** nisso."
)

f1, f2 = st.columns([3, 2])
regiao = f1.selectbox("Sua região", list(M.REGIOES), index=0)
plantio = f2.date_input("Data do plantio", value=date.today(), format="DD/MM/YYYY")
cal_col, ceasa_padrao = M.REGIOES[regiao]
f3, f4 = st.columns([3, 2])
ceasas = sorted(df["ceasa"].unique())
ceasa = f3.selectbox("Onde você quer comparar o preço (Ceasa)", ceasas, index=ceasas.index(ceasa_padrao))
criterio = f4.radio("O que é \"compensar\" para você?",
                    ["Preço mais alto na venda", "Mais estável (menos risco)", "Maior lucro estimado por hectare"])
with st.expander("⚙️ Ajustes do cálculo"):
    g1, g2, g3, g4 = st.columns(4)
    desconto = g1.slider("Produtor recebe quanto a menos que a Ceasa (%)", 0, 50, M.DESCONTO_PADRAO) / 100
    usar_perdas = g2.toggle("Descontar as perdas típicas de cada cultura", value=True,
                            help="Ex.: alho 20%, cenoura e cebola 15%, outras 10%. Valores em dados\\perdas.csv.")
    inflacao = g3.slider("Inflação esperada (% ao ano)", 0.0, 15.0, M.INFLACAO_PADRAO, step=0.5) / 100
    metodo = g4.selectbox("Preço normal", M.METODOS)

# ---------- Cálculo ----------
linhas = []
for _, c in cult.iterrows():
    mod = M.modelo_produto(mensal, pl, c["produto"])
    if mod is None:
        continue
    ciclo, jan = M.ciclo_janela(c, plantio)  # verão/inverno conforme o mês do plantio
    colheita = plantio + timedelta(days=ciclo)
    R = M.cenarios(mod, colheita, jan)
    if R.empty:
        continue
    E = M.esperado(R)
    pn, _, _ = M.preco_normal(mensal, mod, c["produto"], ceasa, colheita + timedelta(days=jan // 2), metodo, inflacao)
    _, un = M.serie_local(mensal, c["produto"], ceasa)
    k, n = int((R > 1).sum()), len(R)
    linha = {
        "produto": c["produto"], "Cultura": c["nome"],
        "recomendado": c[cal_col][plantio.month - 1] == "1",
        "colheita": colheita, "meses": M.meses_da_venda(colheita, jan),
        "E": E, "R": R, "k": k, "n": n, "seguro": M.wilson_inferior(k, n),
        "conf": M.confianca(mod), "fonte": mod["fonte"], "mod": mod,
        "esperado": pn * E, "unidade": UNIDADES.get(un, "") if un else "",
        "lucro_ha": float("nan"), "custo_kg": float("nan"),
    }
    cs = custos[custos["produto"] == c["produto"]] if len(custos) else pd.DataFrame()
    if len(cs) and pd.notna(pn) and un == "KG":
        cs = cs.iloc[0]
        perda = M.perdas_de(perdas, c["produto"])[0] if usar_perdas else 0.0
        prod_t = float(cs["produtividade_t_ha"])
        linha["lucro_ha"] = M.lucro_ha(pn * E, desconto, prod_t, perda, float(cs["custo_ha_2026"]))
        linha["custo_kg"] = float(cs["custo_ha_2026"]) / (prod_t * 1000 * (1 - perda))
    linhas.append(linha)
res = pd.DataFrame(linhas)
if criterio.startswith("Preço"):
    res = res.sort_values("E", ascending=False)
elif criterio.startswith("Mais"):
    # menos risco = primeiro a confiança na época, depois o limite conservador da chance de vender acima do normal
    res = res.assign(_c=res["conf"].map({"Alta": 2, "Média": 1, "Baixa": 0}))
    res = res.sort_values(["_c", "seguro", "E"], ascending=[False, False, False]).drop(columns="_c")
else:
    res = res.sort_values(["lucro_ha", "E"], ascending=[False, False], na_position="last")

aba1, aba2 = st.tabs(["📋 Todas as culturas", "⚖️ Comparar até 3 culturas"])

# ---------- Aba 1: ranking ----------
with aba1:
    so_boas = st.toggle("Mostrar só as culturas em boa época de plantio na minha região", value=True)
    tab = res[res["recomendado"]] if so_boas else res
    st.markdown(
        f'<p class="dica">Ordenado por <b>{criterio.lower()}</b>. <b>Preço na venda</b>: quanto o preço costuma ficar acima (▲) '
        "ou abaixo (▼) do preço normal nos meses de venda. <b>Anos acima do normal</b>: em quantos anos do histórico isso "
        "aconteceu. <b>Confiança</b>: o quanto o desenho da época se repete entre os anos (mais anos = mais confiável).</p>",
        unsafe_allow_html=True,
    )
    mostrar = pd.DataFrame({
        "Cultura": tab["Cultura"],
        "Confiança": tab["conf"].map(SELO),
        "Época na região": tab["recomendado"].map({True: "✅ Boa", False: "⚠️ Fora"}),
        "Colheita a partir de": pd.to_datetime(tab["colheita"]).dt.strftime("%d/%m/%Y"),
        "Venda em": tab["meses"].map(lambda v: " · ".join(MESES[x - 1] for x in v)),
        "Preço na venda": ((tab["E"] - 1) * 100).map(pct),
        "Anos acima do normal": [f"{k} de {n}" for k, n in zip(tab["k"], tab["n"])],
        f"Preço esperado ({ceasa.title()})": [f"{brl(p)} / {u}" if u and pd.notna(p) else "sem dados"
                                              for p, u in zip(tab["esperado"], tab["unidade"])],
        "Custo por kg vendido": tab["custo_kg"].map(lambda v: "—" if pd.isna(v) else brl(v)),
        "Lucro esperado / ha": tab["lucro_ha"].map(lambda v: "—" if pd.isna(v) else brl(v, 0)),
        "Base do histórico": tab["fonte"],
    })
    st.dataframe(mostrar, hide_index=True, width="stretch", height=min(38 * (len(mostrar) + 1), 760))
    st.caption(
        f"Preço esperado = preço normal na Ceasa (sem época, corrigido pela inflação) × média dos anos do histórico nos meses de "
        f"venda. Lucro = preço esperado × (1 − {desconto:.0%}) × produtividade × (1 − perdas) − custo por hectare. "
        "\"Mais estável\" usa um limite conservador: 3 de 3 anos vale menos que 9 de 9, porque com poucos anos o acaso pesa mais."
    )
    if tab.empty:
        st.info("Nenhuma cultura em boa época nesta data. Desligue o filtro acima para ver todas.")

# ---------- Aba 2: comparar ----------
with aba2:
    nomes = res["Cultura"].tolist()
    sugeridas = res.loc[res["recomendado"], "Cultura"].tolist()[:3] or nomes[:3]
    escolha = st.multiselect("Escolha até 3 culturas", nomes, default=sugeridas, max_selections=3)
    if escolha:
        cols = st.columns(len(escolha))
        for col, nome in zip(cols, escolha):
            r = res[res["Cultura"] == nome].iloc[0]
            with col:
                st.markdown(
                    f'<div class="cartao"><div class="rotulo">{nome} · confiança {SELO[r["conf"]]}</div>'
                    f'<div class="valor">{pct((r["E"] - 1) * 100)}</div><div class="detalhe">preço na venda vs normal</div></div>'
                    f'<div class="cartao"><div class="rotulo">Anos acima do normal</div><div class="valor">{r["k"]} de {r["n"]}</div>'
                    f'<div class="detalhe">chance de ser só acaso: {M.chance_acaso(r["k"], r["n"]):.0%}</div></div>'
                    f'<div class="cartao"><div class="rotulo">Colheita e venda</div><div class="valor">{r["colheita"]:%d/%m/%Y}</div>'
                    f'<div class="detalhe">venda em {" · ".join(MESES[x - 1] for x in r["meses"])} · '
                    f'{"✅ boa época" if r["recomendado"] else "⚠️ fora da época"}</div></div>'
                    f'<div class="cartao"><div class="rotulo">Preço esperado — {ceasa.title()}</div>'
                    f'<div class="valor">{brl(r["esperado"])}</div><div class="detalhe">por {r["unidade"] or "—"}</div></div>',
                    unsafe_allow_html=True,
                )
                if pd.notna(r["lucro_ha"]):
                    cor = "#4cc38a" if r["lucro_ha"] >= 0 else "#e66767"
                    st.markdown(f'<div class="cartao"><div class="rotulo">Lucro esperado por hectare</div>'
                                f'<div class="valor" style="color:{cor}">{brl(r["lucro_ha"], 0)}</div>'
                                f'<div class="detalhe">custo {brl(r["custo_kg"])}/kg vendido</div></div>', unsafe_allow_html=True)
        st.markdown('<p class="dica">A linha mostra a <b>época</b> de cada cultura (0% = preço normal). Os <b>pontos grandes</b> '
                    "são os meses em que você estaria vendendo.</p>", unsafe_allow_html=True)
        fig = go.Figure()
        fig.add_hline(y=0, line=dict(color="#6b6a63", width=1, dash="dot"))
        for cor, nome in zip(CORES, escolha):
            r = res[res["Cultura"] == nome].iloc[0]
            idx = r["mod"]["indice"]
            fig.add_trace(go.Scatter(
                x=MESES, y=(idx.values - 1) * 100, name=nome, mode="lines+markers", line=dict(color=cor, width=2.5),
                marker=dict(size=[14 if m in r["meses"] else 6 for m in range(1, 13)], color=cor, line=dict(color=FUNDO, width=2)),
                hovertemplate=f"{nome}: %{{y:+.0f}}%<extra></extra>"))
        fig.update_layout(paper_bgcolor=FUNDO, plot_bgcolor=FUNDO, font=dict(color=TEXTO, size=13), height=420,
                          margin=dict(l=10, r=10, t=10, b=10), hovermode="x unified",
                          legend=dict(orientation="h", y=1.08, x=0, font=dict(color=TEXTO_2)),
                          hoverlabel=dict(bgcolor="#262624", font_color=TEXTO))
        fig.update_xaxes(showgrid=False, linecolor=GRADE, tickfont=dict(color=TEXTO_2))
        fig.update_yaxes(gridcolor=GRADE, zeroline=False, ticksuffix="%", tickfont=dict(color=TEXTO_2),
                         title=dict(text="acima / abaixo do normal", font=dict(color=TEXTO_2)))
        st.plotly_chart(fig, width="stretch")
    else:
        st.info("Escolha pelo menos uma cultura.")

# ---------- Custos e avisos ----------
if len(custos):
    with st.expander("💰 Custos de produção usados"):
        tc = pd.DataFrame({
            "Cultura": custos["produto"].str.title(),
            "Custo 2017 (R$/ha)": custos["custo_ha_2017"].map(lambda v: brl(v, 0)),
            "Custo 2026 (R$/ha)": custos["custo_ha_2026"].map(lambda v: brl(v, 0)),
            "Subiu desde 2017": ((custos["custo_ha_2026"] / custos["custo_ha_2017"] - 1) * 100).map(
                lambda v: "—" if pd.isna(v) else f"+{v:.0f}%"),
            "Faixa nas fontes (R$/ha)": [f"{brl(a, 0)} a {brl(b, 0)}" for a, b in zip(custos["custo_ha_min"], custos["custo_ha_max"])],
            "Produtividade (t/ha)": custos["produtividade_t_ha"],
            "Fontes": custos["fonte"],
        })
        st.dataframe(tc, hide_index=True, width="stretch")
        st.caption("Para mudar um custo ou a produtividade, edite o arquivo dados\\custos.csv.")

n_baixa = int((res["conf"] == "Baixa").sum())
st.markdown(
    f'<div class="aviso">⚠️ <b>Versão de teste.</b> {n_baixa} de {len(res)} culturas têm <b>confiança baixa</b>: a Conab só tem '
    "dados de jun/2022 a dez/2025, pouco para firmar a época. Alho e cenoura usam sua planilha de BH desde 2017 e são as mais "
    "confiáveis. Ciclos, épocas de plantio, produtividade e perdas são <b>estimativas</b> — confira com um agrônomo.</div>",
    unsafe_allow_html=True,
)
