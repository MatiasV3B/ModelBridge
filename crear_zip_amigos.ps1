<#
.SYNOPSIS
    Crea un archivo ZIP limpio listo para compartir con amigos.
#>

$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $ProjectDir) { $ProjectDir = Get-Location }

$ZipPath = Join-Path $ProjectDir "AntigravityBridge-Windows.zip"
$TempStaging = Join-Path $env:TEMP "AntigravityBridge_Package"

Write-Host "Preparando paquete para compartir..." -ForegroundColor Cyan

if (Test-Path $TempStaging) {
    Remove-Item $TempStaging -Recurse -Force
}
New-Item -ItemType Directory -Path $TempStaging | Out-Null

$FilesToCopy = @(
    "Instalador-AntigravityBridge.bat",
    "Iniciar-AntigravityBridge.bat",
    "Iniciar-AntigravityBridge.vbs",
    "Iniciar-Servicio-Fondo.bat",
    "Detener-Servicio-Fondo.bat",
    "LEEME-INSTRUCCIONES.txt",
    "README.md",
    "main.py",
    "requirements.txt",
    "install.ps1"
)

foreach ($f in $FilesToCopy) {
    $src = Join-Path $ProjectDir $f
    if (Test-Path $src) {
        Copy-Item -Path $src -Destination (Join-Path $TempStaging $f)
    }
}

$DirsToCopy = @("core", "server", "gui", "tests")
foreach ($d in $DirsToCopy) {
    $srcDir = Join-Path $ProjectDir $d
    if (Test-Path $srcDir) {
        Copy-Item -Path $srcDir -Destination (Join-Path $TempStaging $d) -Recurse
    }
}

# Eliminar __pycache__ y *.pyc del staging
Get-ChildItem -Path $TempStaging -Include "__pycache__" -Recurse -Force | Remove-Item -Recurse -Force
Get-ChildItem -Path $TempStaging -Include "*.pyc" -Recurse -Force | Remove-Item -Force

if (Test-Path $ZipPath) {
    Remove-Item $ZipPath -Force
}

Write-Host "Comprimiendo en AntigravityBridge-Windows.zip..." -ForegroundColor Yellow
Compress-Archive -Path "$TempStaging\*" -DestinationPath $ZipPath -CompressionLevel Optimal

# Limpiar staging
Remove-Item $TempStaging -Recurse -Force

$SizeMB = [math]::Round((Get-Item $ZipPath).Length / 1MB, 2)
Write-Host "[OK] Archivo ZIP creado con exito!" -ForegroundColor Green
Write-Host "Ubicacion: $ZipPath ($SizeMB MB)" -ForegroundColor Cyan
