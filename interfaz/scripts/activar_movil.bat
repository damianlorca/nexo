@echo off
rem Publica la web de NEXO en la red privada de Tailscale (https://<pc>.<tailnet>.ts.net) para el movil.
rem Solo dentro de la tailnet: es "serve", NUNCA "funnel" (funnel la abriria a internet).
rem La web sigue escuchando solo en 127.0.0.1:8765; Serve hace de puente HTTPS.
rem Se hace UNA vez: Tailscale lo recuerda tras reiniciar. Quitarlo: quitar_movil.bat.
set "TS=tailscale"
where tailscale >nul 2>nul || set "TS=%ProgramFiles%\Tailscale\tailscale.exe"
"%TS%" serve --bg --https=443 http://127.0.0.1:8765
echo.
"%TS%" serve status
pause
