# Autoarranque de la interfaz web de NEXO: Tarea Programada "NEXO interfaz".
# Lanza el vigia (interfaz\vigia.py) con pythonw: el vigia arranca la web y la relanza si cae,
# salvo que la pararas a proposito (parar_interfaz.bat). Corre como TU usuario, sin elevar, y solo
# con la sesion iniciada (NEXO usa la GUI: nada de servicio).
#
# Disparadores (T1028, 24/10): el PC casi nunca se reinicia, solo se suspende, y un vigia lanzado desde
# la app de Claude muere con ella. Por eso, ademas de al iniciar sesion, la tarea salta al DESBLOQUEAR
# la sesion (vuelta de suspender) y cada 10 minutos. Nunca hay dos vigias: el Programador ignora el
# disparo si su vigia sigue vivo (IgnoreNew) y el propio vigia se retira si otro tiene su candado
# (nucleo.instancia.unico("nexo_interfaz_vigia")).
#
# El disparador "al iniciar sesion" suele pedir administrador PARA REGISTRARLO (una vez): si da
# "Acceso denegado", abre PowerShell como administrador y vuelve a ejecutar este script.
# -Simular: ensena lo que registraria sin tocar nada.
# Para quitarla: schtasks /Delete /TN "NEXO interfaz" /F
param([switch]$Simular)
$ErrorActionPreference = "Stop"
$raiz = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$pyw = Join-Path $raiz ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $pyw)) { throw "No encuentro $pyw" }
$usuario = "$env:USERDOMAIN\$env:USERNAME"

$accion = New-ScheduledTaskAction -Execute $pyw -Argument "-m interfaz.vigia" -WorkingDirectory $raiz
$alIniciar = New-ScheduledTaskTrigger -AtLogOn -User $usuario
# StateChange 8 = SessionUnlock (New-ScheduledTaskTrigger no lo ofrece: se crea la clase CIM a mano).
$claseSesion = Get-CimClass -Namespace Root/Microsoft/Windows/TaskScheduler -ClassName MSFT_TaskSessionStateChangeTrigger
$alDesbloquear = New-CimInstance -CimClass $claseSesion -ClientOnly -Property @{ StateChange = 8; UserId = $usuario; Enabled = $true }
# Sin RepetitionDuration la repeticion es indefinida.
$cada10 = New-ScheduledTaskTrigger -Once -At (Get-Date).Date -RepetitionInterval (New-TimeSpan -Minutes 10)
$disparadores = @($alIniciar, $alDesbloquear, $cada10)
$quien = New-ScheduledTaskPrincipal -UserId $usuario -LogonType Interactive -RunLevel Limited
# Sin limite de tiempo (el vigia vive toda la sesion); si el vigia muriera, el Programador lo
# reintenta 3 veces cada minuto; nunca dos vigias a la vez.
$ajustes = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew `
  -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
  -StartWhenAvailable

if ($Simular) {
  "SIMULACION (no se registra nada) para $usuario"
  "Accion: $pyw -m interfaz.vigia (en $raiz)"
  "Disparadores: al iniciar sesion | al desbloquear (StateChange=$($alDesbloquear.StateChange)) | cada $($cada10.Repetition.Interval)"
  "Instancias: $($ajustes.MultipleInstances)"
  exit 0
}

try {
  Register-ScheduledTask -TaskName "NEXO interfaz" -Force -Action $accion -Trigger $disparadores -Principal $quien `
    -Settings $ajustes -Description "Vigia de la interfaz web de NEXO (arranca y relanza la web; respeta parar_interfaz.bat). Salta al iniciar sesion, al desbloquear y cada 10 min; una sola instancia." | Out-Null
} catch {
  if ($_.Exception.Message -match "denegado|denied|0x80070005") {
    Write-Host "Acceso denegado: registra la tarea UNA vez desde PowerShell como administrador." -ForegroundColor Yellow
    Write-Host "La tarea correra igualmente como $usuario, sin privilegios."
    exit 1
  }
  throw
}
$t = Get-ScheduledTask -TaskName "NEXO interfaz"
"NEXO interfaz: $($t.State); salta al iniciar sesion, al desbloquear y cada 10 min ($usuario)."
"Para arrancarla ya sin cerrar sesion: Start-ScheduledTask -TaskName 'NEXO interfaz'"
