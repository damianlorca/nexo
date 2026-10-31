@echo off
rem Deja de publicar la web de NEXO en la tailnet (el movil ya no entra). El PC sigue igual.
rem Solo quita el puerto 443; no toca otros "serve" que puedas tener.
set "TS=tailscale"
where tailscale >nul 2>nul || set "TS=%ProgramFiles%\Tailscale\tailscale.exe"
"%TS%" serve --https=443 off
echo.
"%TS%" serve status
pause
