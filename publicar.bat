@echo off
rem Atualiza o painel na internet: exporta os dados publicos (sem a planilha propria) e envia ao GitHub.
rem O Streamlit Cloud percebe a mudanca e atualiza o site sozinho em 1 a 3 minutos.
cd /d "%~dp0"
".venv\Scripts\python.exe" coleta\exportar_online.py
if errorlevel 1 goto erro
git add online dados\eventos.csv dados\culturas.csv dados\custos.csv dados\perdas.csv
git commit -m "Atualiza dados do painel online"
git push
if errorlevel 1 goto erro
echo.
echo Pronto. O site atualiza em 1 a 3 minutos.
pause
exit /b 0
:erro
echo.
echo Deu erro. Copie a mensagem acima e mostre ao Claude.
pause
exit /b 1
