# Instala Graft (@nanonets/graft 0.19.0) con un Node 22 LTS PORTATIL propio.
#
# Por que (23/09): con el Node 26 del sistema la compilacion de las gramaticas
# de tree-sitter falla en Windows (LNK1117 'opt:lldltojobs': Node 26 se compila
# con clang-cl y pasa flags de LTO que el enlazador de MSVC no entiende). Node 22
# LTS se compila con MSVC, asi que sus addons compilan bien. No se toca el Node
# del sistema: todo vive en C:\Users\damia\Desktop\AI\herramientas\.
#
# Pasos (se para al primer fallo): descargar Node 22 -> verificar SHA-256 contra
# SHASUMS256.txt oficial -> instalar graft en un prefijo propio con telemetria
# apagada -> construir el grafo de NEXO (sin LLM) -> consulta de prueba ->
# registrar el MCP 'graft' en Claude Desktop (copia de seguridad antes, UTF-8 sin BOM).

$ErrorActionPreference = "Stop"
$env:DO_NOT_TRACK = "1"
$REPO  = "C:\Users\damia\Desktop\AI\agente"
$BASE  = "C:\Users\damia\Desktop\AI\herramientas"
$NODE_DIR = Join-Path $BASE "node22"
$GRAFT_PREFIX = Join-Path $BASE "graft"
New-Item -ItemType Directory -Force $BASE, $GRAFT_PREFIX | Out-Null

# 1) Node 22 portatil
$node = Join-Path $NODE_DIR "node.exe"
if (-not (Test-Path $node)) {
    $shas = (Invoke-WebRequest -UseBasicParsing "https://nodejs.org/dist/latest-v22.x/SHASUMS256.txt").Content
    $linea = ($shas -split "`n") | Where-Object { $_ -match "node-v22\.\d+\.\d+-win-x64\.zip$" } | Select-Object -First 1
    if (-not $linea) { throw "No encuentro el zip win-x64 de Node 22 en SHASUMS256.txt" }
    $hashEsperado, $zipNombre = ($linea.Trim() -split "\s+")
    $zip = Join-Path $BASE $zipNombre
    Write-Host "Descargando $zipNombre ..."
    Invoke-WebRequest -UseBasicParsing "https://nodejs.org/dist/latest-v22.x/$zipNombre" -OutFile $zip
    $hash = (Get-FileHash $zip -Algorithm SHA256).Hash.ToLower()
    if ($hash -ne $hashEsperado.ToLower()) { Remove-Item $zip; throw "SHA-256 NO coincide: $hash vs $hashEsperado" }
    Write-Host "SHA-256 verificado: $hash"
    Expand-Archive $zip -DestinationPath $BASE -Force
    Move-Item (Join-Path $BASE ($zipNombre -replace "\.zip$","")) $NODE_DIR
    Remove-Item $zip
}
Write-Host "Node portatil: $(& $node -v)"

# 2) Graft con el npm de ese Node, en su prefijo.
# El node-gyp que trae Node 22 (v11.5) no reconoce Visual Studio 2026 (v18):
# se usa el node-gyp 12 del Node del sistema, que si lo encuentra, pero compilando
# contra las cabeceras de Node 22 (sin los flags de LTO de clang de Node 26).
$gyp12 = "C:\Program Files\nodejs\node_modules\npm\node_modules\node-gyp\bin\node-gyp.js"
if (Test-Path $gyp12) { $env:npm_config_node_gyp = $gyp12 }
# Un intento anterior a medias se aparta (no se borra).
if (Test-Path (Join-Path $GRAFT_PREFIX "node_modules")) {
    Rename-Item $GRAFT_PREFIX "graft_intento_$(Get-Date -Format HHmmss)"
    New-Item -ItemType Directory -Force $GRAFT_PREFIX | Out-Null
}
$npmCli = Join-Path $NODE_DIR "node_modules\npm\bin\npm-cli.js"
$env:PATH = "$NODE_DIR;$env:PATH"
# npm ignora npm_config_node_gyp para los scripts de instalacion de las gramaticas
# (siguen llamando al node-gyp 11, que no reconoce VS 2026). Asi que: instalar SIN
# scripts (de paso no se manda el evento de telemetria del postinstall) y compilar a
# mano cada addon nativo con Node 22 + node-gyp 12.
& $node $npmCli install -g --prefix $GRAFT_PREFIX --ignore-scripts "@nanonets/graft@0.19.0"
if ($LASTEXITCODE -ne 0) { throw "npm install --ignore-scripts de graft fallo" }
$raizMods = Join-Path $GRAFT_PREFIX "node_modules\@nanonets\graft\node_modules"
$addons = Get-ChildItem $raizMods -Recurse -Filter binding.gyp -Depth 3 | ForEach-Object { $_.Directory.FullName } | Sort-Object -Unique
Write-Host "Addons nativos a compilar: $($addons.Count)"
foreach ($dir in $addons) {
    Push-Location $dir
    Write-Host "  compilando $(Split-Path $dir -Leaf) ..."
    # PowerShell 5.1 convierte cualquier linea de stderr en error con Stop:
    # node-gyp escribe hasta "gyp info ok" por stderr. Se relaja SOLO aqui y
    # se decide por el codigo de salida real.
    $ErrorActionPreference = "Continue"
    $logAddon = Join-Path $BASE ("gyp_" + (Split-Path $dir -Leaf) + ".log")
    & $node $gyp12 rebuild --release *> $logAddon
    $codigo = $LASTEXITCODE
    $ErrorActionPreference = "Stop"
    Write-Host "    codigo $codigo (log: $logAddon)"
    Pop-Location
    if ($codigo -ne 0) { throw "fallo compilando $dir" }
}
& $node (Join-Path $GRAFT_PREFIX "node_modules\@nanonets\graft\dist\cli.js") --version
if ($LASTEXITCODE -ne 0) { throw "graft no arranca tras compilar los addons" }
$cli = Join-Path $GRAFT_PREFIX "node_modules\@nanonets\graft\dist\cli.js"
if (-not (Test-Path $cli)) { throw "No encuentro $cli" }

# 3) Telemetria off + grafo (solo capa estructural)
& $node $cli telemetry disable
& $node $cli build $REPO
if ($LASTEXITCODE -ne 0) { throw "graft build fallo" }

# 4) Prueba real
# Ojo: cortar la salida con Select-Object -First mata el proceso y da codigo != 0.
$salidaAsk = & $node $cli ask "donde se decide el proveedor de fallback en el router" $REPO | Out-String
($salidaAsk -split "`n" | Select-Object -First 12) -join "`n" | Write-Host
if ($LASTEXITCODE -ne 0) { throw "graft ask fallo" }

# 5) Registrar el MCP en Claude Desktop
$cfgPath = Join-Path $env:APPDATA "Claude\claude_desktop_config.json"
Copy-Item $cfgPath "$cfgPath.antes_de_graft_$(Get-Date -Format yyyyMMdd_HHmmss).bak"
$cfg = Get-Content $cfgPath -Raw | ConvertFrom-Json
$srv = [pscustomobject]@{ command = $node; args = @($cli, "mcp", $REPO); env = [pscustomobject]@{ DO_NOT_TRACK = "1" } }
$cfg.mcpServers | Add-Member -NotePropertyName "graft" -NotePropertyValue $srv -Force
[System.IO.File]::WriteAllText($cfgPath, ($cfg | ConvertTo-Json -Depth 10), (New-Object System.Text.UTF8Encoding($false)))
Write-Host "Servidores MCP: $(($cfg.mcpServers.PSObject.Properties.Name) -join ', ')"
Write-Host "GRAFT_OK"
