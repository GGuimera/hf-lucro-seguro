"""Entrada do painel "Preço Seguro": junta as páginas num menu.

Como abrir (dentro da pasta do projeto):
    .venv\\Scripts\\streamlit.exe run painel\\inicio.py
"""
import sys
from pathlib import Path

import streamlit as st

sys.path.append(str(Path(__file__).resolve().parent))
from modelo import ONLINE  # no site público a metodologia de previsão fica escondida

st.set_page_config(page_title="Preço Seguro", page_icon="🌱", layout="wide")

MENU = {
    "Hortifrúti (HF)": [("app.py", "Preços", "📊"), ("plantar.py", "O que plantar agora", "🌱"),
                        ("analise.py", "Análise por cultura (modelo preditivo)", "🔬"),
                        ("clima.py", "Clima e alertas nos polos", "🌦️"),
                        ("clima_preco.py", "O clima explica o preço? (prova)", "🧪"),
                        ("noticias.py", "Notícias × preços", "📰")],
    "Agro": [("agro.py", "Commodities: grãos, café, boi, adubo", "🚜")],
    "Ciência": [("artigos.py", "Artigos científicos", "📚")],
    "Confiança": [("confiabilidade.py", "Dá para confiar? (provas e fontes)", "✅")],
}
OCULTAS_ONLINE = {"plantar.py", "analise.py", "clima_preco.py", "confiabilidade.py"}  # páginas de previsão/metodologia
menu = {grupo: [st.Page(arq, title=t, icon=i, default=(arq == "app.py")) for arq, t, i in itens
                if not (ONLINE and arq in OCULTAS_ONLINE)] for grupo, itens in MENU.items()}
pagina = st.navigation({g: ps for g, ps in menu.items() if ps})
pagina.run()
