@echo off
rem Rotina diaria do Preco Seguro: noticias, commodities do agro, clima dos polos (HF + agro) e artigos cientificos.
cd /d "%~dp0.."
".venv\Scripts\python.exe" coleta\buscar_noticias.py
".venv\Scripts\python.exe" coleta\commodities.py
".venv\Scripts\python.exe" coleta\clima.py
".venv\Scripts\python.exe" coleta\artigos.py
rem Interpretacao com IA: so roda se houver ANTHROPIC_API_KEY no arquivo .env (sem a chave nao faz nada).
".venv\Scripts\python.exe" coleta\artigos_ia.py
