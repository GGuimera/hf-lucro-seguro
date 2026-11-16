"""Entrada do painel "Preço Seguro": junta as páginas num menu.

Como abrir (dentro da pasta do projeto):
    .venv\\Scripts\\streamlit.exe run painel\\inicio.py
"""
import sys
from pathlib import Path

import streamlit as st

sys.path.append(str(Path(__file__).resolve().parent))
from modelo import ONLINE
import membros
import pagina_inicial

st.set_page_config(page_title="Preço Seguro", page_icon="🌱", layout="wide")

MENU = {
    "Hortifrúti (HF)": [("app.py", "Preços", "📊"), ("plantar.py", "O que plantar agora", "🌱"),
                        ("analise.py", "Análise por cultura (modelo preditivo)", "🔬"),
                        ("clima.py", "Clima e alertas nos polos", "🌦️"),
                        ("clima_preco.py", "O clima explica o preço? (prova)", "🧪"),
                        ("fatores.py", "Fatores de mercado explicam o preço? (prova)", "🧮"),
                        ("noticias.py", "Notícias × preços", "📰")],
    "Agro": [("agro.py", "Commodities: grãos, café, boi, adubo", "🚜")],
    "Forragem hidropônica": [("forragem.py", "Viabilidade de forragem hidropônica", "🌾")],
    "Ciência": [("artigos.py", "Artigos científicos", "📚")],
    "Confiança": [("confiabilidade.py", "Dá para confiar? (provas e fontes)", "✅")],
}
PUBLICAS = {"app.py", "noticias.py", "clima.py", "agro.py", "artigos.py"}  # o que todo visitante vê
landing = st.Page(pagina_inicial.renderizar, title="Início", icon="🏠", default=True)
grupos = {"Geral": [landing]}
for grupo, itens in MENU.items():
    visiveis = [(arq, t, i) for arq, t, i in itens if arq in PUBLICAS or membros.logado()]
    if visiveis:
        grupos[grupo] = [st.Page(arq, title=t, icon=i) for arq, t, i in visiveis]
st.navigation(grupos).run()
