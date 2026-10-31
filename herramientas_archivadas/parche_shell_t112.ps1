# Parche T112 (v2) para manos/shell.py -- lo ejecuta Damian (shell.py es
# archivo blindado: un agente no se lo modifica a si mismo).
# Fuerza UTF-8 en la consola de PowerShell que abre _powershell(), para que
# los acentos no salgan como mojibake. Prefijo probado el 23/09 a traves de
# la propia herramienta comando(): acentos correctos en Get-Content y Python.
#
# La v1 no hizo nada al pegarla porque shell.py usa CRLF y el texto pegado
# venia con LF; esta version normaliza los finales de linea antes de comparar.
# Es seguro repetirlo: si ya esta parcheado, no toca nada.
#
# Uso (desde la carpeta agente):
#   powershell -ExecutionPolicy Bypass -File parche_shell_t112.ps1
# Despues hay que reiniciar Claude Desktop para que el servidor MCP cargue
# el cambio (igual que tras instalar Graft: se puede hacer una sola vez).

$ruta = "C:\Users\damia\Desktop\AI\agente\manos\shell.py"

$original = @'
def _powershell(comando: str) -> list[str]:
    return [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy", "Bypass",
        "-Command", comando,
    ]
'@

$nuevo = @'
_FIJAR_ENCODING = (
    "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
    "$OutputEncoding = [System.Text.Encoding]::UTF8; "
    "$PSDefaultParameterValues['*:Encoding'] = 'UTF8'; "
)


def _powershell(comando: str) -> list[str]:
    return [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy", "Bypass",
        "-Command", _FIJAR_ENCODING + comando,
    ]
'@

$contenidoCRLF = [System.IO.File]::ReadAllText($ruta, [System.Text.Encoding]::UTF8)
$contenido = $contenidoCRLF -replace "`r`n", "`n"
$originalLF = $original -replace "`r`n", "`n"
$nuevoLF = $nuevo -replace "`r`n", "`n"

if ($contenido.Contains($nuevoLF)) {
    Write-Host "Ya estaba parcheado. No se ha tocado nada."
    exit 0
}

if (-not $contenido.Contains($originalLF)) {
    Write-Host "AVISO: no he encontrado el texto original. No he tocado el archivo. Avisa a Claude."
    exit 1
}

$respaldo = "C:\Users\damia\Desktop\AI\agente\manos\shell.py.bak_t112"
[System.IO.File]::WriteAllText($respaldo, $contenidoCRLF, (New-Object System.Text.UTF8Encoding $false))
Write-Host "Respaldo guardado en: $respaldo"

$parcheadoCRLF = ($contenido.Replace($originalLF, $nuevoLF)) -replace "`n", "`r`n"
[System.IO.File]::WriteAllText($ruta, $parcheadoCRLF, (New-Object System.Text.UTF8Encoding $false))

Write-Host "Parcheado: $ruta"
Write-Host "Verifica con:  git -C 'C:\Users\damia\Desktop\AI\agente' diff -- manos/shell.py"
