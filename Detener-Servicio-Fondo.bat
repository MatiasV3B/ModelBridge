@echo off
cd /d "%~dp0"
:: Cierra el Bridge de esta carpeta: el que corre con su .venv y tambien el que se abrio con otro Python
:: (por ejemplo "pythonw main.py" con el Python del sistema). No toca otros programas Python.
powershell -NoProfile -Command "$dir = '%~dp0'; $venv = $dir + '.venv\'; $main = $dir + 'main.py'; Get-CimInstance Win32_Process | Where-Object { ($_.ExecutablePath -and $_.ExecutablePath.StartsWith($venv, [StringComparison]::OrdinalIgnoreCase)) -or ($_.CommandLine -and $_.CommandLine.IndexOf($main, [StringComparison]::OrdinalIgnoreCase) -ge 0) } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
exit /b 0
