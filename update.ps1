<#
.SYNOPSIS
    Actualiza Antigravity Bridge: descarga el codigo nuevo, sincroniza el entorno y lo reinicia.
.DESCRIPTION
    - Cierra el Bridge si esta corriendo (solo el de esta carpeta).
    - Si es un clon de git hace "git pull"; si no, descarga el ZIP de GitHub y lo superpone
      (sin tocar .env ni .venv).
    - Ejecuta "uv sync": solo instala lo que cambio (rapido).
    - Vuelve a iniciar el Bridge.
#>

param(
    [switch]$NoRestart
)

$ErrorActionPreference = "Stop"
$RepoZip = "https://github.com/MatiasV3B/ModelBridge/archive/refs/heads/main.zip"
$Dir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Dir

Write-Host "=== Actualizando Antigravity Bridge ===" -ForegroundColor Cyan

# 1. Cerrar el Bridge de esta carpeta
$venvPrefix = (Join-Path $Dir ".venv") + "\"
Get-CimInstance Win32_Process |
    Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith($venvPrefix, [System.StringComparison]::OrdinalIgnoreCase) } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

# 2. Actualizar el codigo
$hasGit = (Test-Path (Join-Path $Dir ".git")) -and (Get-Command git -ErrorAction SilentlyContinue)
if ($hasGit) {
    Write-Host "[1/3] git pull..." -ForegroundColor Yellow
    & git pull --ff-only
    if ($LASTEXITCODE -ne 0) { throw "git pull fallo. Resuelve los cambios locales y vuelve a intentar." }
} else {
    Write-Host "[1/3] Descargando la ultima version..." -ForegroundColor Yellow
    $TmpZip = Join-Path $env:TEMP "AntigravityBridge-main.zip"
    $TmpDir = Join-Path $env:TEMP "AntigravityBridge-extract"
    Invoke-WebRequest -Uri $RepoZip -OutFile $TmpZip -UseBasicParsing
    if (Test-Path $TmpDir) { Remove-Item $TmpDir -Recurse -Force }
    Expand-Archive -Path $TmpZip -DestinationPath $TmpDir -Force
    $Extracted = Get-ChildItem $TmpDir -Directory | Select-Object -First 1
    & robocopy $Extracted.FullName $Dir /E /XD .venv .git /XF .env /NFL /NDL /NJH /NJS /NP | Out-Null
    Remove-Item $TmpZip, $TmpDir -Recurse -Force -ErrorAction SilentlyContinue
}

# 3. Sincronizar el entorno: install.ps1 reutiliza uv y solo instala lo que cambio
Write-Host "[2/3] Sincronizando entorno (uv sync)..." -ForegroundColor Yellow
& (Join-Path $Dir "install.ps1") -NoLaunch
if (-not (Test-Path (Join-Path $Dir ".venv\Scripts\pythonw.exe"))) { throw "No se pudo preparar el entorno." }

# 4. Reiniciar
if (-not $NoRestart) {
    Write-Host "[3/3] Iniciando Antigravity Bridge..." -ForegroundColor Yellow
    Start-Process -FilePath (Join-Path $Dir ".venv\Scripts\pythonw.exe") -ArgumentList "`"$(Join-Path $Dir 'main.py')`"" -WorkingDirectory $Dir
}
Write-Host "[OK] Antigravity Bridge actualizado." -ForegroundColor Green
