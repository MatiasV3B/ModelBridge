@echo off
cd /d "%~dp0"
taskkill /f /im pythonw.exe 2>nul
exit /b 0
