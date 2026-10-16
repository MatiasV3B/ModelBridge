<#
.SYNOPSIS
    Actualiza Antigravity Bridge: descarga el codigo nuevo, sincroniza el entorno y lo reinicia.
.DESCRIPTION
    - Cierra el Bridge si esta corriendo (solo el de esta carpeta).
    - Si es un clon de git hace "git pull"; si no, descarga el ZIP de GitHub y lo superpone
      (sin tocar .env ni .venv).
    - Vuelve a preparar Python con install.ps1 y el MISMO modo con que se instalo (.install-mode):
      seguro = "uv sync" en el .venv; normal = "pip install" en el Python del sistema. Solo instala lo que cambio.
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

# 1. Cerrar el Bridge de esta carpeta: el que corre con su .venv (modo seguro) y el que corre con el Python del
#    sistema (modo normal), que se reconoce porque su linea de comandos apunta al main.py de esta carpeta
$venvPrefix = (Join-Path $Dir ".venv") + "\"
$mainPy = Join-Path $Dir "main.py"
Get-CimInstance Win32_Process |
    Where-Object {
        ($_.ExecutablePath -and $_.ExecutablePath.StartsWith($venvPrefix, [System.StringComparison]::OrdinalIgnoreCase)) -or
        ($_.CommandLine -and $_.CommandLine.IndexOf($mainPy, [System.StringComparison]::OrdinalIgnoreCase) -ge 0)
    } |
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

# 3. Sincronizar Python: install.ps1 reutiliza el modo guardado (.install-mode) y solo instala lo que cambio
Write-Host "[2/3] Sincronizando dependencias..." -ForegroundColor Yellow
& (Join-Path $Dir "install.ps1") -NoLaunch
$Pythonw = Join-Path $Dir ".venv\Scripts\pythonw.exe"
$SavedPython = Join-Path $Dir ".python-path"
if (Test-Path $SavedPython) { $Pythonw = (Get-Content $SavedPython -TotalCount 1).Trim() }
if (-not (Test-Path $Pythonw)) { throw "No se pudo preparar el entorno." }

# 4. Reiniciar
if (-not $NoRestart) {
    Write-Host "[3/3] Iniciando Antigravity Bridge..." -ForegroundColor Yellow
    Start-Process -FilePath $Pythonw -ArgumentList "`"$(Join-Path $Dir 'main.py')`"" -WorkingDirectory $Dir
}
Write-Host "[OK] Antigravity Bridge actualizado." -ForegroundColor Green
