# Genera los iconos de la app movil (PWA) a partir del logo de NEXO. Sin dependencias: System.Drawing de Windows.
# Uso:  powershell -NoProfile -ExecutionPolicy Bypass -File interfaz\scripts\generar_iconos.ps1 [-Logo RUTA]
# Salida: interfaz\estatico\iconos\nexo-192.png, nexo-512.png (purpose "any") y nexo-maskable-192/512.png
# (purpose "maskable": el dibujo encogido dentro de la zona segura, para que Android lo recorte en circulo
# sin cortar las bolas de las esquinas). Para cambiar el logo: otra imagen cuadrada y volver a ejecutarlo.
param(
    [string]$Logo = (Join-Path $PSScriptRoot "..\..\..\logonexo.jpeg")
)
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing

$salida = Join-Path $PSScriptRoot "..\estatico\iconos"
New-Item -ItemType Directory -Force -Path $salida | Out-Null
# Fondo en degradado diagonal como el del logo (#41414b arriba-izq. -> #22222a abajo-der.), extrapolado para
# que en el borde del dibujo encogido (maskable) coincida con el del logo y no se vea el cuadrado.
$fondoIni = [System.Drawing.ColorTranslator]::FromHtml("#494953")
$fondoFin = [System.Drawing.ColorTranslator]::FromHtml("#1a1a21")

$src = [System.Drawing.Bitmap]::FromFile((Resolve-Path $Logo))
try {
    if ($src.Width -ne $src.Height) { throw "El logo tiene que ser cuadrado ($($src.Width)x$($src.Height))" }
    # Recorte al dibujo: quita el borde del cuadrado redondeado (~10% por lado en el logo de 1129 px).
    $m = [int]($src.Width * 0.098)
    $recorte = New-Object System.Drawing.Rectangle $m, $m, ($src.Width - 2 * $m), ($src.Height - 2 * $m)

    function Guardar([int]$lado, [double]$escala, [string]$nombre) {
        $bmp = New-Object System.Drawing.Bitmap $lado, $lado
        $g = [System.Drawing.Graphics]::FromImage($bmp)
        try {
            $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
            $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
            $g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
            $pincel = New-Object System.Drawing.Drawing2D.LinearGradientBrush (New-Object System.Drawing.Point 0, 0), (New-Object System.Drawing.Point $lado, $lado), $fondoIni, $fondoFin
            $g.FillRectangle($pincel, 0, 0, $lado, $lado)
            $pincel.Dispose()
            $d = [int][math]::Round($lado * $escala)
            $o = [int](($lado - $d) / 2)
            $g.DrawImage($src, (New-Object System.Drawing.Rectangle $o, $o, $d, $d), $recorte, [System.Drawing.GraphicsUnit]::Pixel)
            $ruta = Join-Path $salida $nombre
            $bmp.Save($ruta, [System.Drawing.Imaging.ImageFormat]::Png)
            Write-Output ("{0}  {1} bytes" -f $nombre, (Get-Item $ruta).Length)
        } finally { $g.Dispose(); $bmp.Dispose() }
    }

    Guardar 192 1.0 "nexo-192.png"
    Guardar 512 1.0 "nexo-512.png"
    # Zona segura maskable = circulo del 80%. Las bolas de las esquinas llegan al ~58% del lado desde el
    # centro: con 0.66 quedan dentro (0.58 * 0.66 = 0.38 < 0.40).
    Guardar 192 0.66 "nexo-maskable-192.png"
    Guardar 512 0.66 "nexo-maskable-512.png"
} finally { $src.Dispose() }
