"""Checks the members login with a random password generated in this run (nothing is stored).
Run (inside the project folder):
    .venv\\Scripts\\python.exe tests\\teste_membros.py
"""
import os
import secrets
import sys
from pathlib import Path

PASTA = Path(__file__).resolve().parent.parent
usuario, senha = "teste_" + secrets.token_hex(3), secrets.token_urlsafe(12)
os.environ["MEMBROS_USUARIO"], os.environ["MEMBROS_SENHA"] = usuario, senha

sys.path.insert(0, str(PASTA / "painel"))
import membros  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

assert membros.credenciais_ok(usuario, senha)
assert not membros.credenciais_ok(usuario, senha + "x")
assert not membros.credenciais_ok("outro", senha)
assert not membros.credenciais_ok("", "")

at = AppTest.from_file(str(PASTA / "painel" / "inicio.py"), default_timeout=300).run()
assert not at.exception, [e.value for e in at.exception]
assert any(b.label == "Entrar" for b in at.button), "a página inicial precisa do botão Entrar"

at.button[0].click().run()
at.text_input[0].set_value(usuario)
at.text_input[1].set_value(senha + "x")
[b for b in at.button if b.label == "Entrar"][-1].click().run()
assert any("incorretos" in e.value for e in at.error), "senha errada precisa mostrar erro"

at.text_input[0].set_value(usuario)
at.text_input[1].set_value(senha)
[b for b in at.button if b.label == "Entrar"][-1].click().run()
assert not at.exception, [e.value for e in at.exception]
assert any("logado como membro" in s.value for s in at.success), "senha certa precisa liberar o acesso"

print("ok: login aceita só a senha certa e a página inicial libera o sistema completo")
