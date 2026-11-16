"""Members login. The user name and password come from segredos/.env (or Streamlit secrets), never from the code."""
import hmac
import os
from pathlib import Path

import streamlit as st

ARQUIVO_ENV = Path(__file__).resolve().parent.parent / "segredos" / ".env"


def _carregar_env():
    if not ARQUIVO_ENV.exists():
        return
    for linha in ARQUIVO_ENV.read_text(encoding="utf-8").splitlines():
        if "=" in linha and not linha.lstrip().startswith("#"):
            chave, valor = linha.split("=", 1)
            os.environ.setdefault(chave.strip(), valor.strip().strip('"').strip("'"))


_carregar_env()


def _segredo(nome):
    try:
        if nome in st.secrets:
            return str(st.secrets[nome])
    except Exception:
        pass
    return os.environ.get(nome, "")


def credenciais_ok(usuario, senha):
    usuario_certo, senha_certa = _segredo("MEMBROS_USUARIO"), _segredo("MEMBROS_SENHA")
    if not usuario_certo or not senha_certa:
        return False
    return (hmac.compare_digest(usuario.encode(), usuario_certo.encode())
            and hmac.compare_digest(senha.encode(), senha_certa.encode()))


def logado():
    return bool(st.session_state.get("membro"))


def entrar(usuario, senha):
    if credenciais_ok(usuario, senha):
        st.session_state["membro"] = True
        return True
    return False


def sair():
    st.session_state["membro"] = False
    st.session_state["mostrar_login"] = False
