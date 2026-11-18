"""Landing page: logo, region, login and free-access buttons. Shown before the system."""
from pathlib import Path

import streamlit as st

import membros
import regiao as R

LOGO = str(Path(__file__).resolve().parent / "logo.svg")


def _gratuito():
    st.session_state["gratuito"] = True
    st.session_state["ir_para"] = st.session_state.get("ultima", "app.py")


def _confirmar():
    if membros.entrar(st.session_state.get("usuario", ""), st.session_state.get("senha", "")):
        st.session_state["ir_para"] = st.session_state.get("ultima", "app.py")
        st.session_state["erro_login"] = False
    else:
        st.session_state["erro_login"] = True


def renderizar():
    _, logo_col, _ = st.columns([1, 2, 1])
    logo_col.image(LOGO, width="stretch")
    st.markdown("<p style='text-align:center'>Decida o que plantar e quando vender.</p>", unsafe_allow_html=True)

    if membros.logado():
        st.success("Você está logado como membro.")
        if st.button("Sair"):
            membros.sair()
            st.rerun()
        return

    _, centro, _ = st.columns([1, 2, 1])
    with centro:
        st.markdown(f"**Sua região:** {R.rotulo(R.atual())}")
        ps = R.polos()
        ufs = sorted(ps["uf"].unique())
        uf = st.selectbox("Estado", ufs, index=ufs.index(ps.loc[R.atual(), "uf"]))
        opcoes = ps[ps["uf"] == uf]
        escolhido = st.selectbox("Região de produção", list(opcoes.index), format_func=lambda p: opcoes.loc[p, "nome"],
                                 index=list(opcoes.index).index(R.atual()) if R.atual() in opcoes.index else 0)
        if st.button("Usar esta região", width="stretch"):
            R.escolher(escolhido)
            st.rerun()

        if st.button("Entrar", type="primary", width="stretch"):
            st.session_state["mostrar_login"] = True
        st.button("Gratuito", width="stretch", on_click=_gratuito)

        if st.session_state.get("mostrar_login"):
            with st.form("entrar"):
                st.text_input("Usuário", key="usuario")
                st.text_input("Senha", type="password", key="senha")
                st.form_submit_button("Confirmar", on_click=_confirmar)
            if st.session_state.get("erro_login"):
                st.error("Usuário ou senha incorretos.")
