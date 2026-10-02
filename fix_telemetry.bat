@echo off
echo ============================================================
echo Reparando hook de telemetria de Google Antigravity en Windows...
echo ============================================================

set PLUGIN_DIR=%USERPROFILE%\.gemini\config\plugins\googlecloudtools.datacloud_telemetry

if exist "%PLUGIN_DIR%" (
    echo Eliminando carpeta defectuosa: %PLUGIN_DIR%
    rmdir /s /q "%PLUGIN_DIR%"
    echo [OK] Carpeta de telemetria eliminada con exito.
) else (
    echo [INFO] La carpeta %PLUGIN_DIR% ya no existe.
)

echo.
echo ============================================================
echo Listo. Por favor reinicia la sesion de Antigravity si es necesario.
echo ============================================================
pause
