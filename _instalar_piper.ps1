# Descarga Piper y una voz en espanol.
#
# Aprobado por Damian el 11/09/2026 a las 06:28 ("Si, y Piper tambien").
#
# Va por lanzar() y no por comando() porque son ~80 MB y el puente
# corta a los 50 segundos sin avisar.
#
# No instala nada en el sistema: Piper es un zip que se descomprime y
# ya. Todo cuelga de la carpeta del proyecto, asi que deshacerlo es
# mover piper\ a _archivo\.

$ErrorActionPreference = 'Stop'

$raiz    = 'C:\Users\damia\Desktop\AI\agente'
$destino = Join-Path $raiz 'piper'
$tmp     = Join-Path $raiz '_descargas'

New-Item -ItemType Directory -Force -Path $destino, $tmp | Out-Null

Write-Output "destino: $destino"

# ---------------------------------------------------- 1. el binario

Write-Output "`n[1/3] Buscando la ultima version de Piper..."

$api = 'https://api.github.com/repos/rhasspy/piper/releases/latest'

$release = Invoke-RestMethod -Uri $api -Headers @{
    'User-Agent' = 'nexo-agente'
}

Write-Output "  version: $($release.tag_name)"

$asset = $release.assets |
    Where-Object { $_.name -match 'windows.*(amd64|x64).*\.zip$' } |
    Select-Object -First 1

if (-not $asset) {
    Write-Output "  AVISO: no hay asset de Windows en esta release."
    Write-Output "  assets disponibles:"
    $release.assets | ForEach-Object { Write-Output "    - $($_.name)" }
    throw "sin binario de Windows"
}

Write-Output "  asset: $($asset.name)  ($([math]::Round($asset.size/1MB,1)) MB)"

$zip = Join-Path $tmp $asset.name

Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zip

Write-Output "  descargado"

Expand-Archive -Path $zip -DestinationPath $tmp -Force

# El zip trae una carpeta piper\ dentro. Se mueve su contenido.
$dentro = Join-Path $tmp 'piper'

if (Test-Path $dentro) {
    Copy-Item -Path (Join-Path $dentro '*') -Destination $destino -Recurse -Force
} else {
    Copy-Item -Path (Join-Path $tmp '*') -Destination $destino -Recurse -Force `
        -Exclude '*.zip'
}

Write-Output "  descomprimido"

# ------------------------------------------------------- 2. la voz

Write-Output "`n[2/3] Descargando la voz es_ES-sharvard-medium..."

$base = 'https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_ES/sharvard/medium'

foreach ($f in @('es_ES-sharvard-medium.onnx', 'es_ES-sharvard-medium.onnx.json')) {
    $url = "$base/$f`?download=true"
    $out = Join-Path $destino $f

    Write-Output "  $f"

    Invoke-WebRequest -Uri $url -OutFile $out
}

# ---------------------------------------------------- 3. comprobar

Write-Output "`n[3/3] Comprobando..."

$exe = Join-Path $destino 'piper.exe'
$mod = Join-Path $destino 'es_ES-sharvard-medium.onnx'

foreach ($p in @($exe, $mod)) {
    if (Test-Path $p) {
        $mb = [math]::Round((Get-Item $p).Length / 1MB, 1)
        Write-Output "  OK  $p  ($mb MB)"
    } else {
        Write-Output "  FALTA  $p"
    }
}

Write-Output "`ncontenido de piper\:"
Get-ChildItem $destino | Select-Object -ExpandProperty Name |
    ForEach-Object { Write-Output "    $_" }

Write-Output "`nFIN_PIPER"
