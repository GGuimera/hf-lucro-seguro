"""Entrada do painel "Preço Seguro": junta as páginas num menu.

Como abrir (dentro da pasta do projeto):
    .venv\\Scripts\\streamlit.exe run painel\\inicio.py
"""
import streamlit as st

st.set_page_config(page_title="Preço Seguro", page_icon="🌱", layout="wide")

pagina = st.navigation([
    st.Page("app.py", title="Preços", icon="📊", default=True),
    st.Page("plantar.py", title="O que plantar agora", icon="🌱"),
    st.Page("analise.py", title="Análise por cultura (modelo preditivo)", icon="🔬"),
    st.Page("clima.py", title="Clima e alertas nos polos", icon="🌦️"),
    st.Page("clima_preco.py", title="O clima explica o preço? (prova)", icon="🧪"),
    st.Page("noticias.py", title="Notícias × preços", icon="📰"),
    st.Page("confiabilidade.py", title="Dá para confiar? (provas e fontes)", icon="✅"),
])
pagina.run()
