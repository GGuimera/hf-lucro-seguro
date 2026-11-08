@echo off
rem Cria a tarefa "PrecoSeguro_Noticias": busca noticias todo dia as 8h e acrescenta em dados\eventos.csv.
rem Para desfazer, rode desagendar_noticias.bat.
schtasks /Create /TN "PrecoSeguro_Noticias" /SC DAILY /ST 08:00 /TR "\"C:\harness\teste-previsibilidade-precos-agricolas\.venv\Scripts\python.exe\" \"C:\harness\teste-previsibilidade-precos-agricolas\coleta\buscar_noticias.py\""
echo.
schtasks /Query /TN "PrecoSeguro_Noticias"
echo.
pause
