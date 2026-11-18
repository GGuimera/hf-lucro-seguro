"""Entrada do painel "Preço Seguro": landing page, depois as páginas por categoria.

Como abrir (dentro da pasta do projeto):
    .venv\\Scripts\\streamlit.exe run painel\\inicio.py
"""
import sys
from pathlib import Path

import streamlit as st

sys.path.append(str(Path(__file__).resolve().parent))
import membros
import pagina_inicial

st.set_page_config(page_title="Preço Seguro", page_icon="🌱", layout="wide")
st.logo(str(Path(__file__).resolve().parent / "logo.svg"))

CATEGORIAS = {  # mais simples primeiro, dentro de cada categoria
    "Consulta de preços": [("app.py", "Preços", "📊"), ("agro.py", "Commodities: grãos, café, boi, adubo", "🚜"),
                           ("artigos.py", "Artigos científicos", "📚")],
    "Radar de commodities": [("clima.py", "Clima e alertas nos polos", "🌦️"), ("noticias.py", "Notícias × preços", "📰"),
                             ("fatores.py", "Fatores de mercado explicam o preço? (prova)", "🧮")],
    "Ferramentas de decisão": [("plantar.py", "O que plantar agora", "🌱"),
                               ("confiabilidade.py", "Dá para confiar? (provas)", "✅"),
                               ("analise.py", "Análise por cultura (modelo preditivo)", "🔬"),
                               ("clima_preco.py", "O clima explica o preço? (prova)", "🧪"),
                               ("forragem.py", "Viabilidade de forragem hidropônica", "🌾")],
}
PUBLICAS = {"app.py", "noticias.py", "clima.py", "agro.py", "artigos.py"}  # o que o acesso gratuito vê

landing = st.Page(pagina_inicial.renderizar, title="Início", icon="🏠", default=True)
grupos = {"Início": [landing]}
if membros.logado() or st.session_state.get("gratuito"):
    for categoria, itens in CATEGORIAS.items():
        visiveis = [(arq, t, i) for arq, t, i in itens if arq in PUBLICAS or membros.logado()]
        if visiveis:
            grupos[categoria] = [st.Page(arq, title=t, icon=i) for arq, t, i in visiveis]
st.navigation(grupos).run()
