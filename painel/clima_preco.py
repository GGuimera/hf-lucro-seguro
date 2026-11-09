"""Página: o clima nos polos produtores explica o preço? (prova estatística, com correção para muitos testes)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parent))
import clima_preco_calc as C
import modelo as M
from modelo import num

FUNDO, TEXTO, TEXTO_2, GRADE = "#1a1a19", "#f0efec", "#c3c2b7", "#2e2e2b"
AZUL, LARANJA, CINZA = "#3987e5", "#d95926", "#6b6a63"

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


def cartao(rotulo, valor, detalhe=""):
    st.markdown(f'<div class="cartao"><div class="rotulo">{rotulo}</div><div class="valor">{valor}</div>'
                f'<div class="detalhe">{detalhe}</div></div>', unsafe_allow_html=True)


def visual(fig, titulo_y, altura=300, sufixo=""):
    fig.update_layout(paper_bgcolor=FUNDO, plot_bgcolor=FUNDO, font=dict(color=TEXTO, size=13), height=altura,
                      margin=dict(l=10, r=10, t=30, b=10), hovermode="x unified",
                      legend=dict(orientation="h", y=1.14, x=0, font=dict(color=TEXTO_2)),
                      hoverlabel=dict(bgcolor="#262624", font_color=TEXTO))
    fig.update_xaxes(showgrid=False, linecolor=GRADE, tickfont=dict(color=TEXTO_2))
    fig.update_yaxes(gridcolor=GRADE, zeroline=False, tickfont=dict(color=TEXTO_2), ticksuffix=sufixo,
                     title=dict(text=titulo_y, font=dict(color=TEXTO_2)))
    return fig


def p100(v, casas=0):
    return "—" if pd.isna(v) else f"{v * 100:+.{casas}f}%".replace(".", ",").replace("-", "−")


@st.cache_data(show_spinner="Rodando a prova em todas as culturas (uns 10 segundos)…")
def rodar_tudo(_mensal, _pl, chave):
    lim = pd.read_csv(C.LIMITES, sep=";").set_index("produto")
    prods = sorted(set(pd.read_csv(C.POLOS_CULT, sep=";")["produto"]))
    res, info = [], {}
    for p in prods:
        r, tp, onde, clima, adj = C.testar(_mensal, _pl, p, lim)
        info[p] = {"pesos": tp, "onde": onde, "clima": clima, "adj": adj}
        res.append(r)
    R = pd.concat(res, ignore_index=True) if res else pd.DataFrame()
    if len(R):
        R["q"] = C.benjamini_hochberg(R["p"])
    return R, info


_, mensal, cult, pl, _, _ = M.carregar()
nomes = dict(zip(cult["produto"], cult["nome"]))
R, info = rodar_tudo(mensal, pl, (len(mensal), len(pl)))

st.title("🧪 O clima nos polos explica o preço?")
st.markdown(
    "Todo mundo diz que **chuva, geada e calor nas regiões produtoras** mexem no preço da Ceasa. Aqui a gente **testa isso "
    "com os números**, do jeito mais honesto possível: o que os dados confirmam, o que é só sinal e o que pode ser acaso."
)
with st.expander("ℹ️ Como o teste funciona (em 4 passos)", expanded=False):
    st.markdown(
        """
1. **Clima de cada mês nos polos da cultura** (página *Clima e alertas*): chuva acima/abaixo do normal daquele mês, dias de
   geada e de calor forte a mais ou a menos. Cada polo pesa pela parte que tem na produção do Brasil (IBGE).
2. **Preço sem o efeito da época**: quanto o preço ficou acima ou abaixo da média dos 3 meses anteriores — no mesmo mês do
   clima, 1 mês depois e 2 meses depois.
3. **Prova contra o acaso**: medimos a correlação (de −1 a +1) e comparamos com o que acontece quando ligamos o preço ao
   clima de **outros meses** (que não podem ter causado aquele preço). Se a relação real não se destaca, pode ser acaso.
4. **Correção para muitos testes**: testamos dezenas de combinações; algumas dão "forte" por sorte. A correção
   (Benjamini-Hochberg) só aprova o que continua forte mesmo assim.
"""
    )

if R.empty:
    st.warning("Ainda não há histórico de clima. Rode coleta\\clima.py.")
    st.stop()

# ---------- 1. Veredito ----------
st.subheader("1. O veredito, sem enfeite")
n = len(R)
fortes = int((R["p"] < 0.05).sum())
aprovados = R[R["q"] < 0.10]
k1, k2, k3 = st.columns(3)
with k1:
    cartao("Combinações testadas", f"{n}", f"{R['produto'].nunique()} culturas × clima × 3 defasagens")
with k2:
    cartao("Deram “forte” (chance de acaso menor que 5%)", f"{fortes}", f"por puro acaso, esperaríamos uns {num(0.05 * n, 0)}")
with k3:
    cartao("Aprovados depois da correção", f"{len(aprovados)}", "relações que se sustentam com segurança")
if aprovados.empty:
    st.markdown(
        '<div class="aviso"><b>Conclusão honesta:</b> com os dados de hoje, <b>não dá para afirmar</b> que o clima do mês nos '
        "polos antecipa o preço na Ceasa. Isso não quer dizer que o clima não importa — quer dizer que os dados ainda são "
        "<b>curtos demais</b> para separar o efeito do clima do sobe-e-desce normal do mercado (a maioria das culturas só tem "
        "uns 40 meses de preço da Conab). Use os alertas de clima como <b>informação</b>, não como previsão de preço.</div>",
        unsafe_allow_html=True)
else:
    st.success("Relações aprovadas mesmo depois da correção: " + "; ".join(
        f"{nomes.get(r.produto, r.produto)} × {C.VARIAVEIS[r.variavel].lower()} ({C.DEFASAGENS[r.k]})" for r in aprovados.itertuples()))

# sinais: mesma direção nas 3 defasagens e pelo menos um p < 0,05
sinais = []
for (prod, var), g in R.groupby(["produto", "variavel"]):
    if len(g) == 3 and (np.sign(g["rho"]).nunique() == 1) and (g["p"] < 0.05).any():
        sinais.append((prod, var, g))
if sinais:
    st.markdown("**Sinais promissores para acompanhar** (mesma direção nas 3 defasagens e pelo menos um teste forte — "
                "ainda **não** é prova):")
    for prod, var, g in sinais:
        m = g.loc[g["p"].idxmin()]
        dirc = "sobe" if m["rho"] > 0 else "cai"
        quando = {"chuva": "chove acima do normal", "geada": "há mais dias de geada que o normal",
                  "calor": "há mais dias de calor forte que o normal"}[var]
        st.markdown(f"- **{nomes.get(prod, prod)}**: quando {quando} "
                    f"nos polos, o preço {dirc} {C.DEFASAGENS[int(m['k'])]}. Nos meses mais extremos (15% mais altos, "
                    f"{int(m['ext_n'])} meses) o preço variou **{p100(m['ext_media'])}**, contra **{p100(m['resto_media'])}** "
                    f"nos demais. Chance de acaso no teste: {num(m['p'] * 100, 0)}%; depois da correção: {num(m['q'] * 100, 0)}%.")

# ---------- 2. Uma cultura em detalhe ----------
st.subheader("2. Uma cultura em detalhe")
prods = sorted(R["produto"].unique(), key=lambda p: nomes.get(p, p))
padrao = "CENOURA" if "CENOURA" in prods else prods[0]
c1, c2, c3 = st.columns(3)
prod = c1.selectbox("Cultura", prods, index=prods.index(padrao), format_func=lambda p: nomes.get(p, p.title()))
vars_ok = [v for v in C.VARIAVEIS if v in set(R.loc[R["produto"] == prod, "variavel"])]
var = c2.selectbox("Clima", vars_ok, format_func=lambda v: C.VARIAVEIS[v])
k = c3.selectbox("Efeito no preço", list(C.DEFASAGENS), index=1, format_func=lambda x: C.DEFASAGENS[x])
I = info[prod]
st.markdown(f'<p class="dica">Preço: <b>{I["onde"]}</b> · Clima: {I["pesos"]}.</p>', unsafe_allow_html=True)
x = I["clima"][var]
y = C.resposta_preco(I["adj"], k)
comum = x.index.intersection(y.index)
x, y = x[comum], y[comum]
linha = R[(R["produto"] == prod) & (R["variavel"] == var) & (R["k"] == k)]
if len(comum) < 24 or linha.empty:
    st.info("Poucos meses com clima e preço ao mesmo tempo para testar esta combinação.")
else:
    L = linha.iloc[0]
    d1, d2, d3, d4 = st.columns(4)
    with d1:
        cartao("Meses comparados", f"{int(L['n'])}", f"{L['ini']} a {L['fim']}")
    with d2:
        cartao("Correlação", num(L["rho"], 2), "de −1 a +1 (0 = nenhuma relação)")
    with d3:
        cartao("Chance de ser acaso", f"{num(L['p'] * 100, 0)}%", f"depois da correção: {num(L['q'] * 100, 0)}%")
    with d4:
        cartao("Depois dos meses mais extremos", p100(L["ext_media"]),
               f"{int(L['ext_n'])} meses · nos demais: {p100(L['resto_media'])}")

    unid = "desvios" if var == "chuva" else "dias"
    xt = [p.to_timestamp() for p in comum]
    f1 = go.Figure(go.Bar(x=xt, y=x.values, marker=dict(color=[AZUL if v >= 0 else LARANJA for v in x.values]),
                          name=C.VARIAVEIS[var], hovertemplate=f"%{{x|%m/%Y}}: %{{y:+.1f}} {unid}<extra></extra>"))
    st.markdown(f'<p class="dica"><b>{C.VARIAVEIS[var]}</b> nos polos, mês a mês (azul = acima do normal, laranja = abaixo).</p>',
                unsafe_allow_html=True)
    st.plotly_chart(visual(f1, unid, altura=230), width="stretch")
    f2 = go.Figure(go.Bar(x=xt, y=y.values * 100, marker=dict(color=[AZUL if v >= 0 else LARANJA for v in y.values]),
                          name="Preço", hovertemplate="%{x|%m/%Y}: %{y:+.0f}%<extra></extra>"))
    st.markdown(f'<p class="dica"><b>Preço {C.DEFASAGENS[k]}</b>, sem o efeito da época, contra a média dos 3 meses anteriores '
                "(cada barra fica no mês do clima, para comparar com o gráfico de cima).</p>", unsafe_allow_html=True)
    st.plotly_chart(visual(f2, "% vs 3 meses antes", altura=230, sufixo="%"), width="stretch")

    f3 = go.Figure(go.Scatter(x=x.values, y=y.values * 100, mode="markers",
                              marker=dict(size=9, color=AZUL, line=dict(color=FUNDO, width=2)),
                              text=[str(p) for p in comum], hovertemplate="%{text}: clima %{x:+.1f} · preço %{y:+.0f}%<extra></extra>"))
    if len(x) >= 3:
        a, b = np.polyfit(x.values, y.values * 100, 1)
        xs = np.linspace(x.min(), x.max(), 20)
        f3.add_trace(go.Scatter(x=xs, y=a * xs + b, mode="lines", line=dict(color=CINZA, width=2, dash="dash"),
                                name="tendência", hoverinfo="skip"))
    f3.update_layout(showlegend=False, hovermode="closest")
    f3.update_xaxes(title=dict(text=f"{C.VARIAVEIS[var]} ({unid})", font=dict(color=TEXTO_2)))
    st.markdown('<p class="dica"><b>Cada ponto é um mês.</b> Se o clima mexesse muito no preço, os pontos formariam uma '
                "faixa inclinada; uma nuvem espalhada quer dizer relação fraca.</p>", unsafe_allow_html=True)
    st.plotly_chart(visual(f3, "preço (%)", altura=320, sufixo="%"), width="stretch")

# ---------- 3. Tabela completa ----------
st.subheader("3. Todos os testes")
T = R.sort_values("p").assign(
    Cultura=lambda d: d["produto"].map(lambda p: nomes.get(p, p.title())),
    Clima=lambda d: d["variavel"].map(C.VARIAVEIS),
    Efeito=lambda d: d["k"].map(C.DEFASAGENS),
)
st.dataframe(pd.DataFrame({
    "Cultura": T["Cultura"], "Clima": T["Clima"], "Efeito no preço": T["Efeito"], "Meses": T["n"],
    "Correlação": T["rho"].map(lambda v: num(v, 2)),
    "Chance de acaso": T["p"].map(lambda v: f"{num(v * 100, 0)}%"),
    "Depois da correção": T["q"].map(lambda v: f"{num(v * 100, 0)}%"),
    "Meses extremos → preço": T["ext_media"].map(p100), "Demais meses → preço": T["resto_media"].map(p100),
}), hide_index=True, width="stretch")

st.subheader("4. Limites desta prova")
st.markdown(
    """
- **Preço curto:** fora alho, cenoura e cebola (planilha de BH desde 2017), o preço vem da média do Brasil da Conab, com uns
  **40 meses** — pouco para separar clima do sobe-e-desce normal. Mais anos (pedido à Conab, sua planilha) deixam a prova mais forte.
- **Mês inteiro:** uma chuva de granizo de um dia some no total do mês. A próxima melhoria é testar por semana.
- **Irrigação e importação:** quase todo hortifrúti é irrigado (a seca pesa menos) e o alho também depende da importação
  (China/Argentina), que o clima daqui não explica.
- **Um ponto por polo:** o clima é do ponto de referência; dentro do polo há variação (altitude, baixadas).
- **Correlação não é causa:** mesmo uma relação aprovada mostra que as coisas andam juntas, não que uma causa a outra.
"""
)
st.caption("Clima: Open-Meteo.com (ERA5/Copernicus) · Produção por município: IBGE PAM · Preços: Conab/Prohort, Ceagesp e planilha de BH.")
