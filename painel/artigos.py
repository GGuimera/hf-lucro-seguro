"""Página: Artigos científicos (de 2010 em diante) por cultura, tema e impacto.
Os artigos são coletados por coleta\\artigos.py (OpenAlex + Embrapa Alice) e ficam na tabela "artigos"."""
import html
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parent))
import modelo as M

FUNDO, TEXTO, TEXTO_2, GRADE, AZUL = "#1a1a19", "#f0efec", "#c3c2b7", "#2e2e2b", "#3987e5"
O_QUE_MUDA = {
    "Pragas e doenças": "pode ajudar a controlar pragas e doenças (e a gastar menos com defensivos)",
    "Plantas daninhas": "pode ajudar no controle do mato",
    "Adubação e solo": "pode ajudar a acertar a adubação e cuidar do solo",
    "Água e irrigação": "pode ajudar a usar melhor a água e a irrigação",
    "Clima": "ajuda a entender o efeito do clima na lavoura",
    "Variedades e melhoramento": "mostra variedades ou materiais genéticos que podem render mais",
    "Pós-colheita e qualidade": "pode ajudar a perder menos depois da colheita e vender com mais qualidade",
    "Custo, preço e mercado": "traz números de custo, preço ou lucro",
    "Manejo e plantio": "pode ajudar no manejo e na época/forma de plantio",
    "Nutrição e manejo animal": "pode ajudar na alimentação e no manejo dos animais",
    "Sustentabilidade": "trata de sustentabilidade (carbono, emissões, integração)",
}

st.markdown(
    """
    <style>
      .block-container {padding-top: 2rem; max-width: 1100px;}
      .art {background:#1f1f1d; border:1px solid #2e2e2b; border-radius:14px; padding:16px 18px; margin:10px 0;}
      .art a.tit {color:#f0efec; font-size:1.05rem; font-weight:650; text-decoration:none;}
      .art a.tit:hover {text-decoration:underline;}
      .art .meta {color:#9a998f; font-size:0.82rem; margin:4px 0 8px;}
      .art .res {color:#e6e5e0; font-size:0.92rem; border-left:3px solid #3987e5; padding:4px 10px; margin:6px 0;}
      .art .muda {color:#c3c2b7; font-size:0.88rem;}
      .chip {display:inline-block; background:#262624; color:#c3c2b7; border-radius:999px; padding:1px 9px; font-size:0.78rem; margin:2px 4px 2px 0;}
      .nota {float:right; font-weight:700; border-radius:10px; padding:2px 10px; font-size:0.9rem;}
      .dica {color:#c3c2b7; font-size:0.92rem;}
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(ttl=3600, show_spinner=False)
def carregar():
    with sqlite3.connect(M.BANCO) as con:
        if not con.execute("SELECT 1 FROM sqlite_master WHERE name='artigos'").fetchone():
            return pd.DataFrame()
        a = pd.read_sql("SELECT * FROM artigos WHERE titulo != ''", con)
    cult = pd.read_csv(M.PASTA / "dados" / "artigos_culturas.csv", sep=";", dtype=str)
    a.attrs["nomes"] = dict(zip(cult["cultura"], cult["nome"]))
    a.attrs["grupos"] = dict(zip(cult["cultura"], cult["grupo"]))
    return a


a = carregar()
st.title("📚 Artigos científicos")
st.markdown(
    '<p class="dica">Pesquisas publicadas de <b>2010 em diante</b> sobre as culturas do sistema, do mundo todo (OpenAlex) e da '
    "<b>Embrapa</b> (repositório Alice). Atualizado pela rotina diária. "
    '<a href="artigos" target="_blank">↗ Abrir esta página numa janela separada</a></p>',
    unsafe_allow_html=True,
)
if a.empty:
    st.warning("Ainda não há artigos. Rode a coleta: `.venv\\Scripts\\python.exe coleta\\artigos.py`.")
    st.stop()

nomes, grupos = a.attrs["nomes"], a.attrs["grupos"]
# só agronomia/pecuária: artigos do OpenAlex precisam ter a subárea registrada (os da Embrapa entram todos)
if "area" in a.columns:
    a = a[a["fonte"].str.contains("Embrapa") | a["area"].fillna("").ne("")]
a["lista_cult"] = a["culturas"].fillna("").str.split("|")
a["lista_temas"] = a["temas"].fillna("").str.split("|").apply(lambda x: [t for t in x if t])

# ---------- filtros ----------
f1, f2 = st.columns([1, 1])
opcoes = sorted({c for cs in a["lista_cult"] for c in cs if c}, key=lambda c: (grupos.get(c, "z"), nomes.get(c, c)))
escolha = f1.multiselect("Cultura", opcoes, format_func=lambda c: f"{nomes.get(c, c)} ({grupos.get(c, '')})",
                         placeholder="Todas as culturas")
temas = f2.multiselect("Tema", list(O_QUE_MUDA), placeholder="Todos os temas")
g1, g2, g3, g4 = st.columns([1.3, 1, 1, 1])
ano_min, ano_max = int(a["ano"].min()), int(a["ano"].max())
anos = g1.slider("Anos", ano_min, ano_max, (ano_min, ano_max))
nota_min = g2.slider("Impacto mínimo", 0, 100, 0, 5, help="Nota de 0 a 100: 60% citações + 40% utilidade prática")
fontes = g3.selectbox("Fonte", ["Todas", "Só Embrapa", "Só OpenAlex (mundo)"])
ordem = g4.selectbox("Ordenar por", ["Maior impacto", "Mais citados", "Mais recentes"])
h1, h2 = st.columns([3, 1])
busca = h1.text_input("Procurar palavra no título ou no resumo", placeholder="ex.: nematoide, irrigação, potássio, Cerrado")
aberto = h2.toggle("Só acesso aberto (grátis)", value=False)

f = a[a["ano"].between(*anos) & (a["impacto"].fillna(0) >= nota_min)]
if escolha:
    f = f[f["lista_cult"].apply(lambda cs: bool(set(cs) & set(escolha)))]
if temas:
    f = f[f["lista_temas"].apply(lambda ts: bool(set(ts) & set(temas)))]
if fontes == "Só Embrapa":
    f = f[f["fonte"].str.contains("Embrapa")]
elif fontes == "Só OpenAlex (mundo)":
    f = f[f["fonte"].str.contains("OpenAlex")]
if busca.strip():
    t = busca.strip().lower()
    f = f[f["titulo"].str.lower().str.contains(t, regex=False) | f["resumo"].fillna("").str.lower().str.contains(t, regex=False)]
if aberto:
    f = f[f["acesso_aberto"] == 1]
col_ord = {"Maior impacto": "impacto", "Mais citados": "citacoes", "Mais recentes": "ano"}[ordem]
f = f.sort_values([col_ord, "impacto"], ascending=False, na_position="last")

# ---------- resumo ----------
c1, c2, c3, c4 = st.columns(4)
c1.metric("Artigos encontrados", f"{len(f):,}".replace(",", "."))
c2.metric("Da Embrapa", f"{int(f['fonte'].str.contains('Embrapa').sum()):,}".replace(",", "."))
c3.metric("Acesso aberto", f"{(f['acesso_aberto'] == 1).mean():.0%}" if len(f) else "—")
c4.metric("Última coleta", pd.to_datetime(a["coletado_em"]).max().strftime("%d/%m/%Y"))

if len(f):
    cont = pd.Series([t for ts in f["lista_temas"] for t in ts]).value_counts()
    if len(cont):
        fig = go.Figure(go.Bar(x=cont.values[::-1], y=cont.index[::-1], orientation="h", marker=dict(color=AZUL, cornerradius=4),
                               hovertemplate="%{y}: %{x} artigos<extra></extra>"))
        fig.update_layout(paper_bgcolor=FUNDO, plot_bgcolor=FUNDO, font=dict(color=TEXTO, size=12), height=260,
                          margin=dict(l=10, r=10, t=10, b=10))
        fig.update_xaxes(gridcolor=GRADE, tickfont=dict(color=TEXTO_2))
        fig.update_yaxes(tickfont=dict(color=TEXTO_2))
        with st.expander("Temas dos artigos encontrados", expanded=False):
            st.plotly_chart(fig, width="stretch")

# ---------- lista ----------
POR_PAG = 20
paginas = max(1, -(-len(f) // POR_PAG))
pag = st.number_input(f"Página (de {paginas})", 1, paginas, 1) if paginas > 1 else 1
for _, r in f.iloc[(pag - 1) * POR_PAG: pag * POR_PAG].iterrows():
    nota = r["impacto"] if pd.notna(r["impacto"]) else 0
    cor = "#4cc38a" if nota >= 60 else "#e0b341" if nota >= 35 else "#9a998f"
    cit = "citações: não informado" if pd.isna(r["citacoes"]) or r["citacoes"] < 0 else f"{int(r['citacoes']):,} citações".replace(",", ".")
    area = r.get("area") if isinstance(r.get("area"), str) and r.get("area") not in ("", "Embrapa") else ""
    meta = " · ".join(filter(None, [str(int(r["ano"])), html.escape(r["revista"] or ""), cit, html.escape(r["fonte"]), html.escape(area),
                                    "🔓 acesso aberto" if r["acesso_aberto"] == 1 else ""]))
    chips = "".join(f'<span class="chip">🌱 {html.escape(nomes.get(c, c))}</span>' for c in r["lista_cult"] if c) + \
        "".join(f'<span class="chip">{html.escape(t)}</span>' for t in r["lista_temas"])
    muda = "; ".join(O_QUE_MUDA[t] for t in r["lista_temas"][:2] if t in O_QUE_MUDA)
    ia = r.get("resumo_ia")
    corpo = (f'<div class="res"><b>Em português simples (IA):</b> {html.escape(ia)}</div>' if isinstance(ia, str) and ia else "")
    if not corpo and isinstance(r["resultado"], str) and r["resultado"]:
        corpo = f'<div class="res"><b>Principal resultado</b> (frase do próprio resumo): {html.escape(r["resultado"])}</div>'
    titulo_nota = "só utilidade prática (sem citações)" if r["so_pratica"] == 1 else "60% citações + 40% utilidade prática"
    st.markdown(
        f'<div class="art"><span class="nota" style="background:{cor}22;color:{cor}" title="{titulo_nota}">{nota:.0f}</span>'
        f'<a class="tit" href="{html.escape(r["url"] or "#")}" target="_blank">{html.escape(r["titulo"])}</a>'
        f'<div class="meta">{html.escape(r["autores"] or "")}<br>{meta}</div>{chips}{corpo}'
        + (f'<div class="muda">💡 O que isso pode mudar: {html.escape(muda)}.</div>' if muda else "") + "</div>",
        unsafe_allow_html=True,
    )
    if isinstance(r["resumo"], str) and r["resumo"]:
        with st.expander("Ver o resumo completo" + (" (em inglês)" if r["idioma"] in ("en", "eng") else "")):
            st.write(r["resumo"])

with st.expander("ℹ️ Como a nota de impacto e a interpretação são feitas"):
    st.markdown(
        """
- **Nota de impacto (0 a 100)** = **60% citações** + **40% utilidade prática**.
  - *Citações*: quantas vezes outros cientistas citaram o artigo **por ano desde que saiu**, comparado com os outros artigos
    da mesma cultura (assim um artigo de 2024 não perde para um de 2011 só por ser novo).
  - *Utilidade prática*: o texto fala de experimento de campo, produtividade, custo/lucro, resultado em %, recomendação, Brasil?
  - Artigos sem número de citações (alguns da Embrapa) recebem só a parte prática (no máximo 70) e isso aparece ao passar o mouse na nota.
- **Temas e "o que isso pode mudar"**: classificação automática por palavras-chave (português e inglês). Pode errar em artigos
  com termos parecidos.
- **Principal resultado**: a frase do próprio resumo com mais sinais de resultado (aumentou, reduziu, %...). Muitos resumos são em
  inglês; a versão com IA (resumo em português simples) pode ser ligada depois.
- **Fontes**: [OpenAlex](https://openalex.org) (catálogo aberto mundial, área de Ciências Agrárias e Biológicas) e
  [Embrapa Alice](https://www.alice.cnptia.embrapa.br) (dados abertos da Embrapa). Os direitos de cada artigo são da revista e dos autores;
  aqui ficam só a referência, o resumo e o link.
"""
    )
