$pluginDir = "$HOME\.gemini\config\plugins\googlecloudtools.datacloud_telemetry"
if (Test-Path $pluginDir) {
    Remove-Item -Recurse -Force $pluginDir
    Write-Host "[OK] Carpeta googlecloudtools.datacloud_telemetry eliminada correctamente." -ForegroundColor Green
} else {
    Write-Host "[INFO] La carpeta ya no existe." -ForegroundColor Yellow
}
