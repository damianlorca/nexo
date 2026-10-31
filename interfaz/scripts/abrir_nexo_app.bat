@echo off
rem Tecla Copilot (PowerToys: Ejecutar programa, ventana oculta) -> NEXO como interruptor (24/10):
rem abre NEXO como aplicacion de Edge con el token de este arranque; si ya esta delante la minimiza y si esta
rem minimizada o detras la trae. La logica esta en interfaz\tecla.py.
cd /d "%~dp0..\.."
start "" ".venv\Scripts\pythonw.exe" -m interfaz.tecla
