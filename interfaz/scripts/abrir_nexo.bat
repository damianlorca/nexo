@echo off
rem Abre la interfaz de NEXO con el token de este arranque (memoria\interfaz_token.txt).
rem El servidor canjea el token por una cookie de sesion y lo quita de la barra al instante.
setlocal
set "TOKEN_FICHERO=%~dp0..\..\memoria\interfaz_token.txt"
if not exist "%TOKEN_FICHERO%" (
  echo La interfaz de NEXO no esta arrancada: no hay token en memoria\interfaz_token.txt
  pause
  exit /b 1
)
set /p TOKEN=<"%TOKEN_FICHERO%"
start "" "http://127.0.0.1:8765/entrar?t=%TOKEN%"
endlocal
