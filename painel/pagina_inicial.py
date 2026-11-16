"""Landing page: what the Preço Seguro is, and the members login button."""
import streamlit as st

import membros


def renderizar():
    st.title("🌱 Preço Seguro")
    st.markdown(
        "Ajuda o produtor rural a decidir **o que plantar e quando vender**, com o histórico de preços das Ceasas, "
        "dos custos de produção e das perdas."
    )

    if membros.logado():
        st.success("Você está logado como membro: o sistema completo está liberado no menu à esquerda.")
        if st.button("Sair"):
            membros.sair()
            st.rerun()
        return

    st.markdown("Acesso livre: as páginas de preços, clima, notícias e artigos. "
                "Para o sistema completo, entre como membro.")
    if st.button("Entrar", type="primary"):
        st.session_state["mostrar_login"] = True

    if st.session_state.get("mostrar_login"):
        with st.form("entrar"):
            usuario = st.text_input("Usuário")
            senha = st.text_input("Senha", type="password")
            if st.form_submit_button("Entrar"):
                if membros.entrar(usuario, senha):
                    st.rerun()
                st.error("Usuário ou senha incorretos.")
