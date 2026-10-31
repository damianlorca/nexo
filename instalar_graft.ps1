# Instala Graft (@nanonets/graft 0.19.0, auditado el 23/09, ver
# contexto/proyectos/nexo/herramientas.md) y lo registra como servidor MCP
# en Claude Desktop, para que las sesiones de Claude consulten el grafo del
# codigo de NEXO en vez de leer archivos enteros (T125).
#
# Que hace, en orden (se para al primer fallo):
#   1. Telemetria apagada ANTES de instalar (el postinstall de npm manda un
#      evento anonimo si no).
#   2. npm install -g de la version exacta auditada.
#   3. graft telemetry disable (persistente) + graft build del repo (solo capa
#      estructural, sin LLM: nada de --deep en este PC sin GPU).
#   4. Prueba real: una consulta al grafo.
#   5. Copia de seguridad de claude_desktop_config.json y alta del servidor
#      "graft" (sin tocar "agente-local").
# NO ejecuta `graft init` (hooks de Claude Code: no hacen falta aqui).
# Despues: cerrar Claude Desktop del todo (tambien desde la bandeja) y abrirlo.

$ErrorActionPreference = "Stop"
$REPO = "C:\Users\damia\Desktop\AI\agente"
$env:DO_NOT_TRACK = "1"

Write-Host "1-2) Instalando @nanonets/graft@0.19.0 (telemetria apagada)..."
npm install -g @nanonets/graft@0.19.0
if ($LASTEXITCODE -ne 0) { throw "npm install fallo (posible falta de binarios de tree-sitter para Node $(node -v))" }

$raizNpm = (npm root -g).Trim()
$cli = Join-Path $raizNpm "@nanonets\graft\dist\cli.js"
if (-not (Test-Path $cli)) { throw "No encuentro $cli" }
$node = (Get-Command node).Source

Write-Host "3) Apagando telemetria de forma persistente y construyendo el grafo..."
& $node $cli telemetry disable
& $node $cli build $REPO
if ($LASTEXITCODE -ne 0) { throw "graft build fallo" }

Write-Host "4) Prueba real de consulta:"
& $node $cli ask "donde se clasifica una tarea en el router" $REPO | Select-Object -First 12
if ($LASTEXITCODE -ne 0) { throw "graft ask fallo" }

Write-Host "5) Registrando el servidor MCP en Claude Desktop..."
$cfgPath = Join-Path $env:APPDATA "Claude\claude_desktop_config.json"
$copia = "$cfgPath.antes_de_graft_$(Get-Date -Format yyyyMMdd_HHmmss).bak"
Copy-Item $cfgPath $copia
$cfg = Get-Content $cfgPath -Raw | ConvertFrom-Json
$srv = [pscustomobject]@{
    command = $node
    args    = @($cli, "mcp", $REPO)
    env     = [pscustomobject]@{ DO_NOT_TRACK = "1" }
}
$cfg.mcpServers | Add-Member -NotePropertyName "graft" -NotePropertyValue $srv -Force
# UTF-8 SIN BOM: Set-Content -Encoding UTF8 de PowerShell 5.1 mete BOM y
# eso puede hacer que Claude Desktop no lea su propio JSON.
[System.IO.File]::WriteAllText($cfgPath, ($cfg | ConvertTo-Json -Depth 10), (New-Object System.Text.UTF8Encoding($false)))
Write-Host "   Copia de seguridad: $copia"
Write-Host "   Servidores ahora: $(($cfg.mcpServers.PSObject.Properties.Name) -join ', ')"

Write-Host ""
Write-Host "HECHO. Cierra Claude Desktop del todo (bandeja incluida) y vuelve a abrirlo."
