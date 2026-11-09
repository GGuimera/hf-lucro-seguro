"""Página "Notícias": eventos de clima, geopolítica, logística e mercado × variação de preço medida nos dados."""
import html
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parent))
import modelo as M
from modelo import MESES, brl

FUNDO, TEXTO, TEXTO_2, GRADE = "#1a1a19", "#f0efec", "#c3c2b7", "#2e2e2b"
TIPOS = {
    "chuva": ("🌧️", "Chuva", "linear-gradient(160deg,#16324f 0%,#1f5c9e 100%)"),
    "frio": ("❄️", "Frio / geada", "linear-gradient(160deg,#1d3346 0%,#4d7fa3 100%)"),
    "calor": ("🔥", "Calor / seca", "linear-gradient(160deg,#4a1d0c 0%,#b5481c 100%)"),
    "geopolitica": ("🌍", "Geopolítica", "linear-gradient(160deg,#2a2150 0%,#6a5bc7 100%)"),
    "logistica": ("🚚", "Logística", "linear-gradient(160deg,#3d2f08 0%,#a87400 100%)"),
    "mercado": ("📦", "Mercado / oferta", "linear-gradient(160deg,#123a2c 0%,#16855e 100%)"),
}

st.markdown(
    """
    <style>
      .block-container {padding-top: 2rem; max-width: 1200px;}
      .grade {display:grid; grid-template-columns:repeat(3, 1fr); gap:6px; margin:8px 0 18px 0;}
      @media (max-width: 760px) { .grade {grid-template-columns:repeat(2, 1fr);} }
      .quadro {position:relative; aspect-ratio:1/1; border-radius:6px; overflow:hidden; display:block;
               text-decoration:none !important; color:#fff !important; transition:transform .15s, filter .15s;}
      .quadro:hover {transform:scale(1.02); filter:brightness(1.12);}
      .quadro .icone {position:absolute; top:22%; left:0; right:0; text-align:center; font-size:3.4rem; opacity:.9;}
      .quadro .selo {position:absolute; top:10px; right:10px; background:rgba(10,10,10,.72); border-radius:999px;
                     padding:4px 10px; font-weight:700; font-size:0.95rem; letter-spacing:.01em;}
      .quadro .data {position:absolute; top:12px; left:12px; font-size:0.78rem; opacity:.85; font-weight:600;}
      .quadro .auto {position:absolute; top:44px; right:10px; background:rgba(224,179,65,.92); color:#1a1a19;
                     border-radius:999px; padding:2px 8px; font-size:0.7rem; font-weight:700;}
      .quadro .rodape {position:absolute; left:0; right:0; bottom:0; padding:30px 12px 10px 12px;
                       background:linear-gradient(transparent, rgba(0,0,0,.82));}
      .quadro .titulo {font-weight:700; font-size:0.98rem; line-height:1.2;}
      .quadro .sub {font-size:0.76rem; opacity:.8; margin-top:3px;}
      .dica {color:#c3c2b7; font-size:0.92rem;}
      .aviso {background:#2a2418; border:1px solid #5c4a1f; border-radius:12px; padding:12px 16px; color:#e8dcc0; font-size:0.88rem;}
    </style>
    """,
    unsafe_allow_html=True,
)

df, mensal, cult, pl, custos, perdas = M.carregar()
ev = M.carregar_eventos()
nomes = dict(zip(cult["produto"], cult["nome"]))
nomes.update({"ALFACE": "Alface", "BATATA": "Batata", "TOMATE": "Tomate"})


@st.cache_data(show_spinner="Medindo o efeito de cada evento nos preços…")
def medir(_ev, chave):  # 'chave' muda quando entram eventos novos, e aí a conta é refeita
    linhas = []
    for _, e in _ev.iterrows():
        for p in e["produtos"]:
            mod = M.modelo_produto(mensal, pl, p)
            r = M.efeito_evento(mensal, mod, p, e["ceasa_medida"], e["mes"])
            linhas.append({"id": e["id"], "produto": p, "efeito": r["efeito"] if r else None,
                           "raridade": r["raridade"] if r else None, "onde": r["onde"] if r else None})
    return pd.DataFrame(linhas)


st.title("📰 Notícias × preços")
st.markdown(
    "Eventos de **clima**, **geopolítica**, **logística** e **mercado** que mexeram com o preço do hortifrúti. "
    "O número no canto de cada quadro é a **variação do preço medida nos nossos dados** logo depois do evento, "
    "**já sem o efeito normal da época**. Toque num quadro para abrir a notícia."
)
if ev.empty:
    st.info("Nenhum evento cadastrado (dados\\eventos.csv).")
    st.stop()

med = medir(ev, tuple(ev["id"]) + tuple(ev["mes"]))
principal = med.dropna(subset=["efeito"]).assign(a=lambda d: d["efeito"].abs()).sort_values("a", ascending=False) \
    .drop_duplicates("id").set_index("id")

f1, f2, f3 = st.columns([2, 2, 1])
tipos_sel = f1.multiselect("Tipo de evento", list(TIPOS), default=list(TIPOS), format_func=lambda t: f"{TIPOS[t][0]} {TIPOS[t][1]}")
culturas = sorted({p for ps in ev["produtos"] for p in ps})
cult_sel = f2.multiselect("Cultura", culturas, format_func=lambda p: nomes.get(p, p.title()),
                          placeholder="Todas as culturas")
ordem = f3.selectbox("Ordenar", ["Mais recentes", "Maior efeito"])
n_auto = int((ev["conferida"] != "sim").sum())
ver_auto = st.toggle(f"Mostrar notícias encontradas automaticamente e ainda não conferidas ({n_auto})", value=True)

mostra = ev[ev["tipo"].isin(tipos_sel)]
if not ver_auto:
    mostra = mostra[mostra["conferida"] == "sim"]
if cult_sel:
    mostra = mostra[mostra["produtos"].map(lambda ps: any(p in cult_sel for p in ps))]
mostra = mostra.assign(ef=mostra["id"].map(principal["efeito"]))
mostra = mostra.sort_values("mes", ascending=False) if ordem == "Mais recentes" else \
    mostra.assign(a=mostra["ef"].abs()).sort_values("a", ascending=False, na_position="last")

quadros = []
for _, e in mostra.iterrows():
    icone, rotulo, fundo = TIPOS.get(e["tipo"], ("📰", e["tipo"], "#333"))
    if e["id"] in principal.index:
        r = principal.loc[e["id"]]
        seta = "▲" if r["efeito"] > 0 else "▼"
        selo = f'{seta} {abs(r["efeito"]):.0%}'
        sub = f'{nomes.get(r["produto"], r["produto"].title())} · {rotulo}'
    else:
        selo, sub = "sem dado", rotulo
    ano, mes = e["mes"][:4], int(e["mes"][5:])
    marca = '<div class="auto">🤖 não conferida</div>' if e["conferida"] != "sim" else ""
    quadros.append(
        f'<a class="quadro" href="{html.escape(e["url"])}" target="_blank" rel="noopener noreferrer" style="background:{fundo}">'
        f'<div class="data">{MESES[mes - 1]}/{ano}</div><div class="selo">{selo}</div>{marca}'
        f'<div class="icone">{icone}</div>'
        f'<div class="rodape"><div class="titulo">{html.escape(e["titulo"])}</div><div class="sub">{html.escape(sub)}</div></div></a>'
    )
st.markdown(f'<div class="grade">{"".join(quadros)}</div>', unsafe_allow_html=True)
st.caption(f"{len(mostra)} eventos · ▲ preço subiu · ▼ preço caiu · \"sem dado\" = ainda não temos preço daquele período.")

# ---------- Detalhe de um evento ----------
st.subheader("🔎 Ver um evento em detalhe")
opcoes = {f'{e["mes"][5:]}/{e["mes"][:4]} — {e["titulo"]}': e["id"] for _, e in ev.sort_values("mes", ascending=False).iterrows()}
esc = st.selectbox("Evento", list(opcoes))
e = ev[ev["id"] == opcoes[esc]].iloc[0]
icone, rotulo, _ = TIPOS.get(e["tipo"], ("📰", e["tipo"], ""))
st.markdown(f"**{icone} {rotulo} · {MESES[int(e['mes'][5:]) - 1]}/{e['mes'][:4]}** — {e['resumo']}  \n"
            f"Fonte: [{e['fonte']}]({e['url']})")
cols = st.columns(len(e["produtos"]))
for col, p in zip(cols, e["produtos"]):
    mod = M.modelo_produto(mensal, pl, p)
    r = M.efeito_evento(mensal, mod, p, e["ceasa_medida"], e["mes"])
    with col:
        if r is None:
            st.markdown(f"**{nomes.get(p, p.title())}**: ainda sem preço desse período no sistema.")
            continue
        vez = "fora do comum" if r["raridade"] <= 0.10 else "comum" if r["raridade"] > 0.30 else "pouco comum"
        st.metric(nomes.get(p, p.title()), f"{r['efeito']:+.0%}", help=f"Medido em: {r['onde']}")
        st.caption(f"Uma variação desse tamanho aconteceu em {r['raridade']:.0%} dos {r['n_meses']} meses do histórico → **{vez}**. "
                   f"Medido em: {r['onde']}.")
        s = r["serie"].dropna()
        t = pd.Period(e["mes"], freq="M")
        janela = s[(s.index >= t - 12) & (s.index <= t + 12)]
        fig = go.Figure(go.Scatter(x=[p_.to_timestamp() for p_ in janela.index], y=janela.values, mode="lines+markers",
                                   line=dict(color="#3987e5", width=2.5), marker=dict(size=6),
                                   hovertemplate="%{x|%m/%Y}: R$ %{y:.2f}<extra></extra>"))
        fig.add_vline(x=t.to_timestamp(), line=dict(color="#e0b341", width=2, dash="dash"))
        fig.add_annotation(x=t.to_timestamp(), y=1.06, yref="paper", text="evento", showarrow=False, font=dict(color="#e0b341"))
        fig.update_layout(paper_bgcolor=FUNDO, plot_bgcolor=FUNDO, font=dict(color=TEXTO, size=12), height=260,
                          margin=dict(l=10, r=10, t=24, b=10), showlegend=False, hoverlabel=dict(bgcolor="#262624"))
        fig.update_xaxes(showgrid=False, tickfont=dict(color=TEXTO_2))
        fig.update_yaxes(gridcolor=GRADE, tickprefix="R$ ", tickfont=dict(color=TEXTO_2))
        st.plotly_chart(fig, width="stretch")

if not M.ONLINE:  # metodologia: só no computador, não no site público
    with st.expander("ℹ️ Como o número de cada quadro é calculado"):
        st.markdown(
            """
1. Pegamos o preço mês a mês da cultura (sua planilha de BH nos anos antigos, a Conab de 2022 a 2025 e os boletins da Ceagesp em 2026).
2. Tiramos o **efeito da época** — se a cenoura sempre sobe em março, essa alta normal não conta.
3. Comparamos os **2 meses depois do evento** com a **média dos 3 meses antes**. O quadro mostra a maior variação nesses 2 meses.
4. Para saber se foi algo especial, contamos em quantos meses do histórico houve uma variação desse tamanho:
   até 10% dos meses = **fora do comum**; mais de 30% = **comum** (pode ser só o sobe-e-desce normal).
"""
        )
st.markdown(
    '<div class="aviso">⚠️ <b>Correlação não é causa.</b> O número mostra o que aconteceu com o preço <b>depois</b> do evento. '
    "Outros fatores podem ter agido ao mesmo tempo (ex.: em março/2022, chuva em São Gotardo e guerra na Ucrânia juntas). "
    "Os resumos foram escritos a partir das notícias; abra a fonte para ler o original. "
    "Para incluir um evento, acrescente uma linha em dados\\eventos.csv.</div>",
    unsafe_allow_html=True,
)
