@echo off
cd /d "%~dp0"
:: Reinicio completo del Bridge: lo cierra del todo (incluido lo que haya quedado ocupando el puerto) y lo abre de nuevo.
call "%~dp0Detener-Servicio-Fondo.bat"
timeout /t 2 /nobreak >nul
call "%~dp0Iniciar-Servicio-Fondo.bat"
exit /b 0
