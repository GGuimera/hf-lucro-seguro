@echo off
rem Rotina diaria do Preco Seguro: noticias + clima dos polos (historico e foto das previsoes).
cd /d "%~dp0.."
".venv\Scripts\python.exe" coleta\buscar_noticias.py
".venv\Scripts\python.exe" coleta\clima.py
