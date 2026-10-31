@echo off
rem Para la web de NEXO A PROPOSITO: el vigia no la relanza hasta seguir_interfaz.bat.
rem (No es la PARADA de NEXO: esa se pone desde la web o con /parar en Telegram.)
cd /d "%~dp0..\.."
".venv\Scripts\python.exe" -m interfaz.vigia --parar
pause
