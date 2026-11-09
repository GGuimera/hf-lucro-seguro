@echo off
rem Liga o painel Preco Seguro neste computador (so este PC acessa) e abre no navegador.
cd /d "%~dp0"
".venv\Scripts\streamlit.exe" run painel\inicio.py --server.address localhost --server.port 8501
pause
