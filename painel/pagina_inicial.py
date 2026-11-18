"""Landing page: logo, login and free-access buttons. Shown before the system."""
import streamlit as st

import membros


def renderizar():
    st.markdown("<h1 style='text-align:center'>🌱 Preço Seguro</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align:center'>Decida o que plantar e quando vender.</p>", unsafe_allow_html=True)

    if membros.logado():
        st.success("Você está logado como membro.")
        if st.button("Sair"):
            membros.sair()
            st.rerun()
        return

    _, centro, _ = st.columns([1, 2, 1])
    with centro:
        if st.button("Entrar", type="primary", width="stretch"):
            st.session_state["mostrar_login"] = True
        if st.button("Gratuito", width="stretch"):
            st.session_state["gratuito"] = True
            st.rerun()

        if st.session_state.get("mostrar_login"):
            with st.form("entrar"):
                usuario = st.text_input("Usuário")
                senha = st.text_input("Senha", type="password")
                if st.form_submit_button("Confirmar"):
                    if membros.entrar(usuario, senha):
                        st.rerun()
                    st.error("Usuário ou senha incorretos.")
