# OBSOLETO desde el 28/09/2026 (T231): los turnos los lanza el planificador de NEXO (nucleo/planificador.py).
# Las tareas "NEXO turno" y "NEXO turno vigilante" estan desactivadas. No volver a registrarlas: con bateria
# Windows dejaba el turno en cola sin arrancar y se lanzarian turnos duplicados.
# T079: turno de NEXO (03:30) + vigilante (04:20). Corte duro a los 60 min (04:30).
# Para quitarlos: schtasks /Delete /TN "NEXO turno" /F ; schtasks /Delete /TN "NEXO turno vigilante" /F
$raiz = "C:\Users\damia\Desktop\AI\agente"
$py = Join-Path $raiz ".venv\Scripts\python.exe"
$aj = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 60) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName "NEXO turno" -Force -Description "Turno de NEXO sin Claude (T079). Parada: /parar." `
  -Action (New-ScheduledTaskAction -Execute $py -Argument "turno_nexo.py --arrancar-chrome" -WorkingDirectory $raiz) `
  -Trigger (New-ScheduledTaskTrigger -Daily -At "03:30") -Settings $aj | Out-Null
$aj2 = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
Register-ScheduledTask -TaskName "NEXO turno vigilante" -Force -Description "Pide cierre suave al turno a las 04:20 (T079)." `
  -Action (New-ScheduledTaskAction -Execute $py -Argument "herramientas_turno\vigilar_turno.py" -WorkingDirectory $raiz) `
  -Trigger (New-ScheduledTaskTrigger -Daily -At "04:20") -Settings $aj2 | Out-Null
Get-ScheduledTask -TaskName "NEXO turno*" | ForEach-Object { "$($_.TaskName): $($_.State), proxima $((Get-ScheduledTaskInfo $_).NextRunTime)" }
