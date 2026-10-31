# Instalacion de ComfyUI para generar imagenes con la GPU integrada
# (AMD Radeon 890M, via DirectML). Pensado para correr desatendido
# con lanzar(): cada paso se registra, y si algo falla se para ahi
# en vez de seguir a ciegas.
#
# Por que DirectML y no CUDA: la GPU es AMD, no NVIDIA. torch-directml
# es la via zero-cost para usar la GPU integrada en Windows sin drivers
# de pago ni hardware nuevo.
#
# extremidades/imagen.py ya habla con ComfyUI por HTTP en
# 127.0.0.1:8188 con el checkpoint sd_xl_turbo_1.0_fp16.safetensors:
# este script deja eso mismo instalado y descargado. Arrancar el
# servidor de ComfyUI (main.py) es un paso aparte, a mano o con
# lanzar(), una vez esto termine bien.

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"  # Invoke-WebRequest sin esto es lentisimo en PS 5.1

$raiz = "C:\Users\damia\Desktop\AI"
$destino = "$raiz\ComfyUI"

function Log($msg) {
    Write-Output "[$(Get-Date -Format 'HH:mm:ss')] $msg"
}

try {
    Log "=== INSTALACION COMFYUI: EMPIEZA ==="

    if (-not (Test-Path $destino)) {
        Log "Clonando ComfyUI desde GitHub..."
        git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git $destino
        if ($LASTEXITCODE -ne 0) { throw "git clone fallo con codigo $LASTEXITCODE" }
        Log "Clonado en $destino"
    } else {
        Log "Ya existe $destino, no clono de nuevo."
    }

    Set-Location $destino

    if (-not (Test-Path "$destino\venv\Scripts\python.exe")) {
        Log "Creando venv propio para ComfyUI (separado del venv del agente)..."
        python -m venv venv
        if ($LASTEXITCODE -ne 0) { throw "creacion del venv fallo" }
    } else {
        Log "El venv ya existe."
    }

    $py = "$destino\venv\Scripts\python.exe"

    Log "Actualizando pip..."
    & $py -m pip install --upgrade pip *> pip_upgrade.log
    if ($LASTEXITCODE -ne 0) { throw "actualizar pip fallo (ver pip_upgrade.log)" }

    Log "Instalando torch-directml (torch + soporte DirectML para la GPU AMD integrada)..."
    & $py -m pip install torch-directml *> pip_torch_directml.log
    if ($LASTEXITCODE -ne 0) { throw "instalar torch-directml fallo (ver pip_torch_directml.log)" }

    Log "Comprobando que torch ve el dispositivo DirectML..."
    & $py -c "import torch_directml; d = torch_directml.device(); print('DirectML device:', d)"
    if ($LASTEXITCODE -ne 0) { throw "torch_directml no reconoce ningun dispositivo" }

    Log "Preparando requirements.txt sin las lineas de torch (ya vienen con torch-directml, no se pueden pisar)..."
    Get-Content requirements.txt | Where-Object { $_ -notmatch '^\s*torch' } | Set-Content requirements_sin_torch.txt

    Log "Instalando el resto de dependencias de ComfyUI..."
    & $py -m pip install -r requirements_sin_torch.txt *> pip_requirements.log
    if ($LASTEXITCODE -ne 0) { throw "instalar requirements.txt fallo (ver pip_requirements.log)" }

    Log "Descargando el checkpoint SDXL Turbo (unos 7 GB, puede tardar bastante)..."
    New-Item -ItemType Directory -Force -Path "$destino\models\checkpoints" | Out-Null
    $checkpoint = "$destino\models\checkpoints\sd_xl_turbo_1.0_fp16.safetensors"

    if (-not (Test-Path $checkpoint)) {
        Invoke-WebRequest `
            -Uri "https://huggingface.co/stabilityai/sdxl-turbo/resolve/main/sd_xl_turbo_1.0_fp16.safetensors" `
            -OutFile $checkpoint
    } else {
        Log "El checkpoint ya existe, no lo descargo de nuevo."
    }

    $tamano = (Get-Item $checkpoint).Length / 1GB
    Log ("Checkpoint en disco: {0:N2} GB" -f $tamano)

    if ($tamano -lt 5) {
        throw "el checkpoint descargado pesa menos de 5 GB: parece incompleto o cortado"
    }

    Log "=== INSTALACION COMFYUI: TERMINADA SIN ERRORES ==="
    Log "Para arrancarlo: $py main.py --directml (desde $destino)"

} catch {
    Log "=== INSTALACION COMFYUI: FALLO ==="
    Log "Error: $_"
    exit 1
}
