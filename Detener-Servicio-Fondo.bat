@echo off
cd /d "%~dp0"
:: Cierra solo el Bridge de esta carpeta (el pythonw.exe de su .venv), no otros programas Python
powershell -NoProfile -Command "$p = (Join-Path '%~dp0' '.venv') + '\'; Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith($p, [StringComparison]::OrdinalIgnoreCase) } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
exit /b 0
