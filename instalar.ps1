# Instalacion del agente. Se ejecuta una vez.
#   cd C:\Users\damia\Desktop\AI\agente
#   .\instalar.ps1

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "=== AGENTE: instalacion ===" -ForegroundColor Cyan
Write-Host ""

# --- Python -------------------------------------------------------
Write-Host "[1/5] Python" -ForegroundColor Yellow

$python = (Get-Command python -ErrorAction SilentlyContinue).Source

if (-not $python -or $python -like "*WindowsApps*") {
    Write-Host "  AVISO: 'python' apunta al alias de Microsoft Store." -ForegroundColor Red
    Write-Host "  Eso cuelga los procesos. Usa la ruta completa o desactiva" -ForegroundColor Red
    Write-Host "  el alias en Configuracion > Alias de ejecucion de aplicaciones." -ForegroundColor Red
} else {
    Write-Host "  $python"
    python --version
}

# --- Dependencias -------------------------------------------------
Write-Host ""
Write-Host "[2/5] Dependencias" -ForegroundColor Yellow

python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requisitos.txt

Write-Host "  instaladas"

# --- Secretos -----------------------------------------------------
Write-Host ""
Write-Host "[3/5] Secretos" -ForegroundColor Yellow

if (-not (Test-Path "secretos.toml")) {
    Copy-Item "secretos.ejemplo.toml" "secretos.toml"
    Write-Host "  creado secretos.toml — pega ahi el token de Telegram" -ForegroundColor Cyan
    Write-Host "  (como conseguirlo: docs\TELEGRAM.md)"
} else {
    Write-Host "  ya existe"
}

# --- Git ----------------------------------------------------------
Write-Host ""
Write-Host "[4/5] Control de versiones" -ForegroundColor Yellow

if (-not (Test-Path ".git")) {
    if (Get-Command git -ErrorAction SilentlyContinue) {
        git init -q
        git add -A
        git commit -q -m "Esqueleto del agente"
        Write-Host "  repositorio creado, primer commit hecho"
    } else {
        Write-Host "  git no esta instalado: winget install Git.Git" -ForegroundColor Red
    }
} else {
    Write-Host "  ya hay repositorio"
}

# --- Comprobacion -------------------------------------------------
Write-Host ""
Write-Host "[5/5] Comprobacion" -ForegroundColor Yellow

$env:PYTHONPATH = $PWD

python -c "from nucleo.config import config; print('  config: OK')"
python -c "from nucleo.permisos import nivel_de_comando; print('  permisos:', nivel_de_comando('pip install x').value, '/', nivel_de_comando('dir').value)"
python -c "from manos import archivos, shell; print('  manos: OK')"
python -c "from canal import buzon; print('  canal: OK')"

Write-Host ""
Write-Host "Inventario de extremidades:" -ForegroundColor Cyan
python extremidades\base.py

Write-Host ""
Write-Host "Listo. Siguiente: docs\ARRANQUE.md" -ForegroundColor Green
Write-Host ""
