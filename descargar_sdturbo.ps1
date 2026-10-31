# Descarga sd-turbo (Stable Diffusion 2.1 Turbo) como checkpoint de repuesto.
#
# Por que: la prueba pruebas/prueba_directml.py del 12/09 midio que la Radeon
# 890M solo admite unos 3 GB por DirectML. SDXL Turbo (6,9 GB, UNet de ~5 GB
# en fp16) no cabe: por eso ComfyUI reventaba con un UnicodeDecodeError que
# escondia el error real del driver. sd-turbo es el mismo truco de pocos pasos
# pero sobre SD 2.1: unos 2,6 GB en fp16, que si entran en 3 GB.

$ErrorActionPreference = "Continue"
$destino = "C:\Users\damia\Desktop\AI\ComfyUI\models\checkpoints\sd_turbo.safetensors"
$log = "C:\Users\damia\Desktop\AI\agente\registros\descargar_sdturbo_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".log"

function Nota($texto) {
    $linea = "[" + (Get-Date -Format "HH:mm:ss") + "] " + $texto
    Write-Output $linea
    Add-Content -Path $log -Value $linea
}

Nota "=== DESCARGA SD-TURBO: EMPIEZA ==="

if (Test-Path $destino) {
    Nota ("Ya estaba en disco: " + [math]::Round((Get-Item $destino).Length / 1GB, 2) + " GB")
} else {
    Nota "Descargando sd_turbo.safetensors (unos 5,2 GB en disco, fp32; ComfyUI lo carga en fp16)..."
    curl.exe -L --silent --show-error -o $destino "https://huggingface.co/stabilityai/sd-turbo/resolve/main/sd_turbo.safetensors" 2>&1 | Add-Content -Path $log
    Nota ("En disco: " + [math]::Round((Get-Item $destino).Length / 1GB, 2) + " GB")
}

Nota "=== DESCARGA SD-TURBO: TERMINADA ==="
Nota "FIN_DESCARGA"
