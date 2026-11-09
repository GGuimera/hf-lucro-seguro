@echo off
rem Cria a tarefa "PrecoSeguro_Noticias": todo dia as 8h roda a rotina diaria (noticias + clima dos polos).
rem Para desfazer, rode desagendar_noticias.bat.
schtasks /Create /F /TN "PrecoSeguro_Noticias" /SC DAILY /ST 08:00 /TR "\"C:\harness\teste-previsibilidade-precos-agricolas\coleta\rotina_diaria.bat\""
echo.
schtasks /Query /TN "PrecoSeguro_Noticias"
echo.
pause
