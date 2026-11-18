@echo off
rem Publicacao diaria automatica (tarefa PrecoSeguro_Publicar): exporta os dados e envia ao GitHub so se houver mudanca.
rem Sem pause: roda pelo agendador do Windows. O publicar.bat continua sendo a versao manual.
cd /d "%~dp0.."
".venv\Scripts\python.exe" coleta\exportar_online.py
if errorlevel 1 exit /b 1
git add online dados\*.csv
git diff --cached --quiet && exit /b 0
git commit -m "Atualiza dados do painel online"
git push
exit /b %errorlevel%
