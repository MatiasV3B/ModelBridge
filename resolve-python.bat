@echo off
:: Lo usan los otros .bat con "call". Deja en PYW la ruta de pythonw.exe de este Bridge:
::   - modo seguro: el del .venv de esta carpeta
::   - modo normal: el Python del sistema que guardo install.ps1 en .python-path
set "PYW=%~dp0.venv\Scripts\pythonw.exe"
if exist "%~dp0.python-path" set /p PYW=<"%~dp0.python-path"
