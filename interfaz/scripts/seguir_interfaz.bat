@echo off
rem Quita la parada a proposito de la web de NEXO y la lanza; el vigia la vuelve a vigilar.
cd /d "%~dp0..\.."
".venv\Scripts\python.exe" -m interfaz.vigia --seguir
pause
