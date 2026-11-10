"""Página: Agro — commodities (grãos, café, açúcar e etanol, pecuária, petróleo e fertilizantes).
Mesmo escopo do HF: época do preço, teste justo de estratégias, lucro por hectare (Conab), clima nos polos e prova
clima × preço."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parent))
import agro_calc as A
import clima_preco_calc as C
import modelo as M
from modelo import MESES, MESES_LONGO, brl

FUNDO, TEXTO, TEXTO_2, GRADE = "#1a1a19", "#f0efec", "#c3c2b7", "#2e2e2b"
AZUL, LARANJA, VERDE, CINZA = "#3987e5", "#d95926", "#199e70", "#6b6a63"

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
      .selo {display:inline-block; padding:2px 10px; border-radius:999px; font-weight:600; font-size:0.85rem;}
    </style>
    """,
    unsafe_allow_html=True,
)


def cartao(rotulo, valor, detalhe="", cor=None):
    estilo = f' style="color:{cor}"' if cor else ""
    st.markdown(f'<div class="cartao"><div class="rotulo">{rotulo}</div><div class="valor"{estilo}>{valor}</div>'
                f'<div class="detalhe">{detalhe}</div></div>', unsafe_allow_html=True)


def visual(fig, titulo_y, altura=380, sufixo="", prefixo=""):
    fig.update_layout(paper_bgcolor=FUNDO, plot_bgcolor=FUNDO, font=dict(color=TEXTO, size=13), height=altura,
                      margin=dict(l=10, r=10, t=30, b=10), hovermode="x unified",
                      legend=dict(orientation="h", y=1.12, x=0, font=dict(color=TEXTO_2)),
                      hoverlabel=dict(bgcolor="#262624", font_color=TEXTO))
    fig.update_xaxes(showgrid=False, linecolor=GRADE, tickfont=dict(color=TEXTO_2))
    fig.update_yaxes(gridcolor=GRADE, zeroline=False, tickfont=dict(color=TEXTO_2), ticksuffix=sufixo,
                     tickprefix=prefixo, title=dict(text=titulo_y, font=dict(color=TEXTO_2)))
    return fig


def num(v, casas=2):
    if pd.isna(v):
        return "—"
    return f"{v:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def preco_txt(v, unidade):
    return f"R$ {num(v, 2 if abs(v) < 100 else 0)} {unidade.replace('R$', '').strip()}"


@st.cache_data(ttl=3600, show_spinner=False)
def dados():
    return A.carregar()


lista, mensal, diario, custos = dados()

st.title("🚜 Agro: commodities")
st.markdown(
    "Grãos, café, açúcar e etanol, pecuária, **petróleo e fertilizantes**, com o mesmo método do HF: "
    "**em que meses o preço costuma ser melhor**, se vale **guardar para vender depois** (ou comprar adubo antes), "
    "**quanto isso muda no lucro por hectare**, o **clima nas regiões produtoras** e se **o clima explica o preço**."
)
if mensal.empty:
    st.warning("Ainda não há dados de commodities. Rode a coleta: `.venv\\Scripts\\python.exe coleta\\commodities.py`.")
    st.stop()

_, ult_ipca = A.ipca_fator(mensal)
st.markdown(f'<p class="dica">Valores "de hoje" = corrigidos pela inflação (IPCA) até {ult_ipca}. '
            "Preços mundiais e de fertilizantes vêm em dólar (Banco Mundial) e são convertidos pelo dólar do mês (Banco Central).</p>",
            unsafe_allow_html=True)

# ---------- 1. Panorama ----------
st.subheader("Panorama: todas as commodities")


@st.cache_data(ttl=3600, show_spinner=False)
def panorama(mensal, lista):
    linhas = []
    for _, it in lista.iterrows():
        s = A.serie(mensal, it["produto"], real=False)
        if len(s) < 24:
            continue
        sr = A.serie(mensal, it["produto"])
        pm, _ = A.indices(sr)
        ult = s.index.max()
        v12 = s.get(ult - 12)
        media5 = sr[sr.index > ult - 60].mean()
        linhas.append({"Grupo": it["grupo"], "Produto": it["nome"], "Último mês": ult.strftime("%m/%Y"),
                       "Preço (média do mês)": preco_txt(s.iloc[-1], it["unidade"]),
                       "Em 12 meses": (s.iloc[-1] / v12 - 1) if v12 else np.nan,
                       "Vs. média de 5 anos (sem inflação)": sr.iloc[-1] / media5 - 1,
                       "Meses mais caros": ", ".join(MESES[m - 1] for m in pm["mean"].nlargest(2).index),
                       "Meses mais baratos": ", ".join(MESES[m - 1] for m in pm["mean"].nsmallest(2).index),
                       "Força da época": pm["mean"].max() - pm["mean"].min()})
    return pd.DataFrame(linhas)


pan = panorama(mensal, lista)
st.dataframe(pan, hide_index=True, width="stretch",
             column_config={"Em 12 meses": st.column_config.NumberColumn(format="percent"),
                            "Vs. média de 5 anos (sem inflação)": st.column_config.NumberColumn(format="percent"),
                            "Força da época": st.column_config.ProgressColumn(
                                format="percent", min_value=0, max_value=0.4,
                                help="Diferença entre o mês mais caro e o mais barato, em média, sem a tendência de longo prazo. "
                                     "No HF chega a 50–100%; nas commodities costuma ser 5–20%.")})
st.caption("Força da época: quanto o mês mais caro costuma ficar acima do mais barato (sem a tendência de longo prazo). "
           "Quanto maior, mais a época importa.")

# ---------- escolha ----------
grupos = list(dict.fromkeys(lista["grupo"]))
c1, c2 = st.columns([1, 2])
grupo = c1.selectbox("Grupo", grupos)
opc = lista[lista["grupo"] == grupo]
nome = c2.selectbox("Produto", list(opc["nome"]))
it = opc[opc["nome"] == nome].iloc[0]
prod, tipo, un = it["produto"], it["tipo"], it["unidade"]
s_nom = A.serie(mensal, prod, real=False)
s = A.serie(mensal, prod)
if len(s) < 36:
    st.warning("Este produto ainda tem menos de 3 anos de dados.")
    st.stop()

# ---------- 2. Preço ----------
st.subheader(f"{nome}: o preço ao longo do tempo")
d = diario[diario["produto"] == prod].sort_values("data") if not diario.empty else pd.DataFrame()
k1, k2, k3, k4 = st.columns(4)
with k1:
    if not d.empty:
        cartao(f"Último preço ({pd.to_datetime(d['data'].iloc[-1]):%d/%m/%Y})", preco_txt(d["valor"].iloc[-1], un), it["unidade"])
    else:
        cartao(f"Média de {s_nom.index.max():%m/%Y}", preco_txt(s_nom.iloc[-1], un), un)
with k2:
    v = s_nom.iloc[-1] / s_nom.get(s_nom.index.max() - 12, np.nan) - 1
    cartao("Em 12 meses", f"{v:+.0%}" if pd.notna(v) else "—", "preço do mês contra o mesmo mês do ano passado")
with k3:
    m5 = s[s.index > s.index.max() - 60].mean()
    cartao("Contra a média de 5 anos", f"{s.iloc[-1] / m5 - 1:+.0%}", "já sem a inflação")
with k4:
    pct_hist = (s < s.iloc[-1]).mean()
    cartao("Posição no histórico", f"{pct_hist:.0%}", f"dos meses desde {s.index.min().year} foram mais baratos (sem inflação)")
real = st.toggle("Mostrar em R$ de hoje (sem inflação)", value=True)
ss = s if real else s_nom
fig = go.Figure(go.Scatter(x=ss.index.to_timestamp(), y=ss.values, mode="lines", line=dict(color=AZUL, width=2), name=nome,
                           hovertemplate="%{x|%m/%Y}: R$ %{y:,.2f}<extra></extra>"))
st.plotly_chart(visual(fig, un + (" (R$ de hoje)" if real else ""), 340, prefixo="R$ "), width="stretch")

# ---------- 3. Época ----------
st.subheader("Em que meses o preço costuma ser melhor")
pm, tab_r = A.indices(s)
forca = pm["mean"].max() - pm["mean"].min()
fig3 = go.Figure(go.Bar(x=[MESES[m - 1] for m in pm.index], y=(pm["mean"] - 1) * 100,
                        marker=dict(color=[AZUL if v >= 1 else LARANJA for v in pm["mean"]], cornerradius=4),
                        customdata=np.c_[pm["vezes_acima"] * 100, pm["count"]],
                        hovertemplate="%{x}: %{y:+.1f}% vs. a média do ano · acima da média em %{customdata[0]:.0f}% dos %{customdata[1]} anos<extra></extra>"))
fig3.add_hline(y=0, line=dict(color="#8a897f", width=1))
st.plotly_chart(visual(fig3, "Preço vs. média do ano", 320, sufixo="%"), width="stretch")
caro = pm["mean"].idxmax()
barato = pm["mean"].idxmin()
st.markdown(
    f'<p class="dica">Em média, <b>{MESES_LONGO[caro - 1]}</b> é o mês mais caro ({(pm.loc[caro, "mean"] - 1):+.1%}, acima da média em '
    f'{pm.loc[caro, "vezes_acima"]:.0%} dos anos) e <b>{MESES_LONGO[barato - 1]}</b> o mais barato ({(pm.loc[barato, "mean"] - 1):+.1%}). '
    f"Força da época: <b>{forca:.0%}</b>{' — fraca: a tendência e os choques (dólar, safra mundial, clima) pesam mais que o mês' if forca < 0.10 else ''}.</p>",
    unsafe_allow_html=True)

# ---------- 4. Teste justo ----------
if not M.ONLINE:  # no site público as estratégias (metodologia de previsão) ficam escondidas
    st.subheader("Vale mudar o mês de vender (ou de comprar)?")
if M.ONLINE:
    pass
elif tipo == "referencia":
    st.info("Este é um preço de referência mundial (ou matéria-prima) que o produtor não compra nem vende diretamente. "
            "Serve para entender o mercado: veja a época acima e a relação de troca abaixo.")
else:
    meses_a = [int(x) for x in it["meses_a"].split("|") if x]
    if tipo == "estocavel":
        st.markdown(f'<p class="dica"><b>A)</b> {it["explica_a"]}. <b>B)</b> guardar e vender nos melhores meses dos 12 seguintes à colheita, '
                    "pagando o custo de guardar (armazém, seguro e o dinheiro parado) por mês.</p>", unsafe_allow_html=True)
        taxa_pad, rot_taxa = 0.8, "Custo de guardar (% do valor por mês)"
    elif tipo == "insumo":
        st.markdown(f'<p class="dica"><b>A)</b> {it["explica_a"]}. <b>B)</b> comprar nos meses mais baratos dos 12 antes de '
                    f'{MESES_LONGO[int(it["mes_alvo"]) - 1]}, pagando o custo do dinheiro parado até o uso.</p>', unsafe_allow_html=True)
        taxa_pad, rot_taxa = 1.0, "Custo do dinheiro (% ao mês)"
    else:
        st.markdown('<p class="dica"><b>A)</b> vender igual em todos os meses. <b>B)</b> concentrar as vendas nos melhores meses '
                    "(ex.: planejar o confinamento ou a estação de monta para vender na entressafra). "
                    "Mudar o mês tem custo (ração, estrutura) que esta conta não inclui.</p>", unsafe_allow_html=True)
        taxa_pad, rot_taxa = 0.0, None
    a1, a2, a3 = st.columns(3)
    k = a1.slider("Quantos meses na estratégia B", 1, 4, 2)
    taxa = a2.slider(rot_taxa, 0.0, 3.0, taxa_pad, 0.1) / 100 if rot_taxa else 0.0
    tab, cont, todos, rotulo = A.teste_justo(s, tipo, meses_a, k, taxa, int(it["mes_alvo"]) if it["mes_alvo"] else None)
    if tab.empty or len(tab) < 3:
        st.warning("Poucos anos completos para o teste.")
    else:
        r = M.resumo_teste(tab["dif"])
        cor_v = "#4cc38a" if "consistente" in r["veredito"] else "#e0b341"
        st.markdown(f'<p class="dica">Meses escolhidos para B (com todos os anos): <b>{", ".join(rotulo(m) for m in todos)}</b>. '
                    f'Veredito: <span class="selo" style="background:{cor_v}22;color:{cor_v}">{r["veredito"]}</span></p>',
                    unsafe_allow_html=True)
        # lucro por hectare (grãos e café, com custo da Conab)
        cst = custos[custos["produto"] == prod] if not custos.empty else pd.DataFrame()
        por_ha = tipo == "estocavel" and not cst.empty
        if por_ha:
            c = cst.iloc[0]
            kg_p, kg_u = A.kg_por_unidade(c["unidade_prod"]), A.kg_por_unidade(un)
            f1, f2, f3 = st.columns(3)
            prod_ha = f1.number_input(f"Produtividade (sacas de {kg_p:.0f} kg por ha)", 1.0, 1000.0, float(c["produtividade"]), 1.0)
            custo_ha = f2.number_input("Custo por hectare (R$)", 0.0, 500000.0, float(c["custo_total_ha"]), 100.0)
            desc = f3.slider("Desconto do preço de referência até a fazenda (frete, base)", 0, 40, 10, 1) / 100
            fator = prod_ha * kg_p / kg_u * (1 - desc)  # unidades de preço vendidas por ha
            la, lb = tab["A"] * fator - custo_ha, tab["B"] * fator - custo_ha
            dif, fmt = lb - la, (lambda v: brl(v, 0))
            st.caption(f"Custo e produtividade padrão: {c['fonte']} — {c['local']}, safra {c['safra']} "
                       f"(custo total, inclui remuneração da terra e do capital). Ajuste para a sua fazenda.")
        else:
            la, lb, dif = tab["A"], tab["B"], tab["dif"]
            fmt = lambda v: preco_txt(v, un) if abs(v) >= 0.005 else "R$ 0"
        v1, v2, v3 = st.columns(3)
        nome_a = "A) Costume" if tipo == "insumo" else ("A) Na colheita" if tipo == "estocavel" else "A) Igual o ano todo")
        with v1:
            cartao(nome_a + (" — lucro/ha" if por_ha else " — preço médio"), fmt(la.mean()), f"pior ano {fmt(la.min())} · melhor {fmt(la.max())}")
        with v2:
            cartao("B) Melhores meses (teste justo)" + (" — lucro/ha" if por_ha else ""), fmt(lb.mean()), f"pior ano {fmt(lb.min())} · melhor {fmt(lb.max())}")
        with v3:
            ganho = dif.mean() if (por_ha or tipo != "insumo") else tab["dif"].mean()
            txt = "economia" if tipo == "insumo" else "ganho"
            cartao(f"B − A ({txt} médio{' por ha' if por_ha else ''})", fmt(ganho) if not por_ha else f"{fmt(ganho)}/ha",
                   f"B foi melhor em {r['k']} de {r['n']} anos · {tab['dif'].mean() / tab['A'].mean():+.1%} no preço",
                   "#4cc38a" if ganho > 0 else "#e66767")
        fig4 = go.Figure()
        fig4.add_trace(go.Bar(x=[str(a) for a in la.index], y=la.values, name=nome_a, marker=dict(color=LARANJA, cornerradius=4)))
        fig4.add_trace(go.Bar(x=[str(a) for a in lb.index], y=lb.values, name="B) Melhores meses (teste justo)",
                              marker=dict(color=AZUL, cornerradius=4)))
        fig4.update_layout(barmode="group", bargap=0.25, bargroupgap=0.08)
        fig4.update_xaxes(type="category", title="Ano da colheita" if tipo == "estocavel" else "Ano do uso" if tipo == "insumo" else "Ano")
        st.plotly_chart(visual(fig4, "Lucro por hectare (R$ de hoje)" if por_ha else f"{un} (R$ de hoje)", 340, prefixo="R$ "), width="stretch")
        u = fmt
        st.markdown(
            f"""
**O quanto dá para confiar:**
- Faixa provável (90%) do {'ganho' if tipo != 'insumo' else 'economia'} médio por ano no preço: **{preco_txt(r['lo'], un)} a {preco_txt(r['hi'], un)}**
  {"(não cruza o zero → diferença consistente)" if r['lo'] > 0 or r['hi'] < 0 else "(cruza o zero → pode ser acaso)"}.
- Chance de uma estratégia ganhar {max(r['k'], r['n'] - r['k'])} de {r['n']} anos **por puro acaso**: **{r['p']:.0%}** (abaixo de 10% é bom sinal).
- Sem o ano mais extremo ({r['ano_ext']}), a diferença média no preço seria **{preco_txt(r['sem_ext'], un)}**.
- Meses que mais entraram em B no teste justo: {", ".join(f"{rotulo(m)} ({n}×)" for m, n in sorted(cont.items(), key=lambda x: -x[1])[:5])}.
"""
        )
        if tipo == "estocavel":
            st.markdown('<div class="aviso">Guardar também é uma <b>aposta</b>: em anos de alta forte (ex.: 2020–2021) guardar rendeu muito; '
                        "em anos de queda, perdeu. Ferramentas que travam o preço (venda antecipada, contratos na B3) mudam essa conta "
                        "e não estão aqui.</div>", unsafe_allow_html=True)

# ---------- 5. Relação de troca ----------
st.subheader("Relação de troca: quantas sacas pagam o adubo")
ferts = lista[lista["produto"].isin(["UREIA", "KCL", "DAP", "TSP"])]
graos = lista[lista["produto"].isin(["SOJA", "MILHO", "CAFE_ARABICA", "CAFE_ROBUSTA", "TRIGO", "ARROZ"])]
t1, t2 = st.columns(2)
fert = t1.selectbox("Adubo", list(ferts["nome"]), index=1)
grao = t2.selectbox("Pago com", list(graos["nome"]), index=0)
fi = ferts[ferts["nome"] == fert].iloc[0]
gi = graos[graos["nome"] == grao].iloc[0]
rel = (A.serie(mensal, fi["produto"], real=False) / A.serie(mensal, gi["produto"], real=False)).dropna()
if len(rel) > 24:
    un_g = gi["unidade"].replace("R$/", "")
    media = rel[rel.index > rel.index.max() - 120].mean()
    r1, r2, r3 = st.columns(3)
    with r1:
        cartao(f"Hoje ({rel.index.max():%m/%Y})", f"{num(rel.iloc[-1], 1)} {un_g}", f"para 1 tonelada de {fert.split(' (')[0].lower()}")
    with r2:
        cartao("Média dos últimos 10 anos", f"{num(media, 1)} {un_g}", f"hoje está {rel.iloc[-1] / media - 1:+.0%} da média",
               "#4cc38a" if rel.iloc[-1] < media else "#e66767")
    with r3:
        pmr, _ = A.indices(rel)
        cartao("Mês em que a troca costuma ser melhor", MESES_LONGO[pmr["mean"].idxmin() - 1],
               f"{pmr['mean'].min() - 1:+.1%} vs. a média do ano · pior: {MESES_LONGO[pmr['mean'].idxmax() - 1]}")
    fig5 = go.Figure(go.Scatter(x=rel.index.to_timestamp(), y=rel.values, mode="lines", line=dict(color=VERDE, width=2),
                                hovertemplate="%{x|%m/%Y}: %{y:.1f}<extra></extra>", name="relação"))
    fig5.add_hline(y=media, line=dict(color="#8a897f", width=1, dash="dot"), annotation_text="média 10 anos",
                   annotation_font_color=TEXTO_2)
    st.plotly_chart(visual(fig5, f"{un_g} por tonelada", 300), width="stretch")
    st.caption("Quanto MENOR, melhor para o produtor (menos sacas para pagar o adubo). Adubo: preço internacional (Banco Mundial) "
               "convertido em reais, sem frete e impostos até a fazenda — serve para comparar épocas, não como preço de compra.")

# ---------- 6. Clima nos polos ----------
st.subheader("Clima nas regiões produtoras (próximos 16 dias)")
polos_df = pd.read_csv(A.POLOS, sep=";")
lim = A.limites()
pol = [p for p in it["polos"].split("|") if p]
if not pol:
    st.info("Este produto não tem região produtora ligada (preço mundial ou insumo).")
else:
    prev = A.previsao_polos(pol)
    if prev.empty:
        st.info("A previsão destas regiões aparece depois da próxima coleta de clima (`coleta\\clima.py`, roda na rotina diária).")
    else:
        lp = lim.loc[prod] if prod in lim.index else None
        linhas = []
        for polo, g in prev.groupby("polo"):
            info = polos_df[polos_df["polo"] == polo].iloc[0]
            por_mod = g.groupby("modelo").agg(tmin=("tmin", "min"), tmax=("tmax", "max"), chuva=("chuva", "sum"))
            alerta = []
            if lp is not None:
                n_geada = int(por_mod["tmin"].le(lp["geada_tmin"]).sum())
                n_calor = int(por_mod["tmax"].ge(lp["calor_tmax"]).sum())
                n_chuva = int(g.groupby("modelo")["chuva"].max().ge(lp["chuva_dia"]).sum())
                if n_geada:
                    alerta.append(f"❄️ geada ({n_geada} de 3 modelos)")
                if n_calor:
                    alerta.append(f"🔥 calor ≥ {lp['calor_tmax']:.0f} °C ({n_calor} de 3)")
                if n_chuva:
                    alerta.append(f"🌧️ chuva ≥ {lp['chuva_dia']:.0f} mm/dia ({n_chuva} de 3)")
            linhas.append({"Região": info["nome"], "Mínima (°C)": f"{por_mod['tmin'].min():.0f} a {por_mod['tmin'].max():.0f}",
                           "Máxima (°C)": f"{por_mod['tmax'].min():.0f} a {por_mod['tmax'].max():.0f}",
                           "Chuva em 16 dias (mm)": f"{por_mod['chuva'].min():.0f} a {por_mod['chuva'].max():.0f}",
                           "Alertas": " · ".join(alerta) or "✅ nada fora do comum"})
        st.dataframe(pd.DataFrame(linhas), hide_index=True, width="stretch")
        st.caption(f"Previsão de {prev['coletado_em'].iloc[0]} · faixa = do modelo mais otimista ao mais pessimista "
                   "(europeu ECMWF, americano GFS e alemão ICON, via Open-Meteo). Limites de alerta: " +
                   (lp["fonte"] if lp is not None else "—") + ".")

# ---------- 7. Clima x preço ----------
if not M.ONLINE:
    st.subheader("O clima nessas regiões explica o preço? (prova)")


@st.cache_data(ttl=6 * 3600, show_spinner="Testando clima × preço em todas as commodities...")
def prova_todas(mensal, lista):
    lim = A.limites()
    partes = []
    for _, x in lista.iterrows():
        t, _, _ = A.prova_clima(mensal, x, lim)
        if not t.empty:
            partes.append(t)
    if not partes:
        return pd.DataFrame()
    t = pd.concat(partes, ignore_index=True)
    t["q"] = C.benjamini_hochberg(t["p"].values)
    return t


tudo = None if M.ONLINE else prova_todas(mensal, lista)
if M.ONLINE:
    pass
elif tudo.empty:
    st.info("A prova aparece quando o histórico de clima das regiões do agro estiver baixado (coleta\\clima.py).")
else:
    n_t, n_p, n_q = len(tudo), int((tudo["p"] < 0.05).sum()), int((tudo["q"] < 0.10).sum())
    p1, p2, p3 = st.columns(3)
    with p1:
        cartao("Testes feitos", f"{n_t}", "commodities × (chuva, geada, calor) × (mesmo mês, 1 e 2 meses depois)")
    with p2:
        cartao("Com sinal (p < 5%)", f"{n_p}", f"por acaso seriam uns {n_t * 0.05:.0f}")
    with p3:
        cartao("Aprovados após a correção", f"{n_q}", "Benjamini-Hochberg, 10% — o que sobra quando se descontam os 'achados de sorte'",
               "#4cc38a" if n_q else "#e0b341")
    meu = tudo[tudo["produto"] == prod].copy()
    if not meu.empty:
        meu["Clima"] = meu["variavel"].map(C.VARIAVEIS)
        meu["Quando o preço reage"] = meu["k"].map(C.DEFASAGENS)
        meu["Correlação"] = meu["rho"].round(2)
        meu["Chance de acaso"] = meu["p"]
        meu["Aprovado?"] = np.where(meu["q"] < 0.10, "✅ sim", np.where(meu["p"] < 0.05, "⚠️ sinal fraco", "—"))
        meu["Preço depois dos meses mais extremos"] = meu["ext_media"]
        st.dataframe(meu[["Clima", "Quando o preço reage", "Correlação", "Chance de acaso", "Preço depois dos meses mais extremos",
                          "Aprovado?"]], hide_index=True, width="stretch",
                     column_config={"Chance de acaso": st.column_config.NumberColumn(format="percent"),
                                    "Preço depois dos meses mais extremos": st.column_config.NumberColumn(format="percent")})
    else:
        st.info("Este produto não tem região de clima ligada.")
    st.caption("Mesmo método da página do HF: o clima de cada mês nas regiões (pesos iguais entre elas) × o preço sem a época "
               "contra a média dos 3 meses anteriores. Commodities têm preço formado no mundo (Chicago, Nova York, dólar), "
               "então o clima de poucas regiões do Brasil explica só uma parte — geadas no café são o exemplo clássico.")

# ---------- 8. Fontes ----------
with st.expander("📚 Fontes e limites"):
    st.markdown(
        """
- **Cepea/Esalq-USP** (via biblioteca aberta *agrobr*, agrobr.dev): indicadores diários de soja (Paranaguá), milho (Campinas),
  trigo (PR), arroz (RS), café arábica e conilon, açúcar cristal, etanol hidratado, boi gordo, bezerro, frango, suíno e leite.
  Licença CC BY-NC 4.0: uso com citação e **sem fins comerciais**.
- **Banco Mundial — Pink Sheet** (CC BY 4.0): petróleo Brent, gás natural, ureia, cloreto de potássio, DAP, TSP, rocha fosfática,
  óleos e preços mundiais, mensais, em dólar.
- **ANP** (via agrobr): diesel S10, média do Brasil. **Banco Central**: dólar (SGS 3698) e IPCA (SGS 433).
- **Conab — Custos de produção**: custo e produtividade padrão de soja, milho safrinha, trigo, arroz irrigado e café.
- **Clima**: Open-Meteo (ERA5/Copernicus e modelos ECMWF, GFS e ICON), nas regiões produtoras de `dados/polos_agro.csv`.
- **Limites:** o preço de referência (porto, praça) não é o preço na sua fazenda; adubo internacional não inclui frete e impostos;
  as estratégias não incluem venda antecipada nem contratos futuros; o histórico não garante o futuro.
"""
    )
