# T134: test de modelos locales supervisado, UNA vez: 24/09/2026 de 05:00 a 06:00 (autorizado por Damian 23/09).
# Quitar: schtasks /Delete /TN "NEXO test modelos" /F
$raiz = "C:\Users\damia\Desktop\AI\agente"
$py = Join-Path $raiz ".venv\Scripts\python.exe"
$accion = New-ScheduledTaskAction -Execute $py -Argument "nucleo\guardia_python.py herramientas_modelos\modelos_supervisado.py --hasta=05:58" -WorkingDirectory $raiz
$disparo = New-ScheduledTaskTrigger -Once -At ([datetime]"2026-09-24T05:00:00")
$aj = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 62) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName "NEXO test modelos" -Action $accion -Trigger $disparo -Settings $aj -Force -Description "Test supervisado de modelos locales (T134), una vez." | Out-Null
Get-ScheduledTask -TaskName "NEXO test modelos" | ForEach-Object { "$($_.TaskName): $($_.State), proxima $((Get-ScheduledTaskInfo $_).NextRunTime)" }
