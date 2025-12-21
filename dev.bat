@echo off
echo 🚀 Iniciando entorno de desarrollo...

REM Activar entorno virtual
call venv\Scripts\activate.bat

REM Ejecutar bot local
python run_local.py

pause