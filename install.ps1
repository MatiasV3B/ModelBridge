<#
.SYNOPSIS
    Instalador completo de Antigravity Bridge para Windows.
.DESCRIPTION
    1. Verifica e instala el CLI de Antigravity (agy).
    2. Instala el SDK de Google Antigravity y todas las dependencias requeridas.
    3. Comprueba el estado de inicio de sesion de Antigravity y permite iniciar sesion.
    4. Crea accesos directos silenciosos en el Escritorio y en el Menu Inicio.
    5. Inicia la aplicacion de forma limpia sin ventanas de terminal.
#>

param(
    [switch]$NoLaunch
)

$ErrorActionPreference = "Stop"

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "      ANTIGRAVITY BRIDGE PARA WINDOWS - INSTALADOR      " -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $ScriptDir) { $ScriptDir = Get-Location }

# 1. Verificar e Instalar Antigravity CLI
Write-Host "[1/5] Comprobando Antigravity CLI (agy)..." -ForegroundColor Yellow
$AgyPath = Join-Path $env:LOCALAPPDATA "agy\bin\agy.exe"

if (Test-Path $AgyPath) {
    Write-Host "  [OK] Antigravity CLI detectado en: $AgyPath" -ForegroundColor Green
} else {
    Write-Host "  [..] Antigravity CLI no encontrado. Instalando automaticamente..." -ForegroundColor Yellow
    try {
        irm https://antigravity.google/cli/install.ps1 | iex
        Write-Host "  [OK] Antigravity CLI instalado con exito." -ForegroundColor Green
    } catch {
        Write-Host "  [!] Advertencia al instalar el CLI: $_" -ForegroundColor DarkYellow
    }
}

# 2. Verificar Python y Dependencias (incluye SDK google-antigravity, FastAPI, CustomTkinter)
Write-Host "[2/5] Verificando entorno Python y SDK..." -ForegroundColor Yellow
$PythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $PythonCmd) {
    Write-Host "  [..] Python no detectado. Intentando instalar Python 3 automaticamente con winget..." -ForegroundColor Cyan
    try {
        winget install Python.Python.3.12 --silent --accept-source-agreements --accept-package-agreements
        Write-Host "  [OK] Python instalado. Actualizando variables de entorno..." -ForegroundColor Green
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
        $PythonCmd = Get-Command python -ErrorAction SilentlyContinue
    } catch {}
}

if (-not $PythonCmd) {
    Write-Host "  [!] No se pudo instalar Python automaticamente." -ForegroundColor Yellow
    Write-Host "  -> Por favor descarga e instala Python (marcando 'Add Python to PATH') desde: https://www.python.org/downloads/" -ForegroundColor Red
    pause
    exit 1
}

$ReqFile = Join-Path $ScriptDir "requirements.txt"
if (Test-Path $ReqFile) {
    Write-Host "  -> Instalando dependencias y SDK de Antigravity..." -ForegroundColor Gray
    & python -m pip install --user -r $ReqFile --quiet
    Write-Host "  [OK] SDK y dependencias instaladas correctamente." -ForegroundColor Green
}

# 3. Comprobar Sesion de Antigravity
Write-Host "[3/5] Comprobando sesion en Google Antigravity..." -ForegroundColor Yellow
$AgyExe = if (Test-Path $AgyPath) { $AgyPath } else { "agy" }
try {
    $out = & $AgyExe models 2>&1
    if ($out.Count -gt 1) {
        Write-Host "  [OK] Sesion activa y verificada en Google Antigravity." -ForegroundColor Green
    } else {
        Write-Host "  [!] No se detecto sesion iniciada en Antigravity." -ForegroundColor Yellow
        Write-Host "  -> Podras iniciar sesion directamente con el boton 'Iniciar Sesion' en la aplicacion." -ForegroundColor Cyan
    }
} catch {
    Write-Host "  [!] Podras iniciar sesion directamente desde la aplicacion." -ForegroundColor DarkYellow
}

# 4. Crear Accesos Directos Silenciosos de Windows (Sin ventanas de terminal)
Write-Host "[4/5] Creando accesos directos silenciosos..." -ForegroundColor Yellow
try {
    $WshShell = New-Object -ComObject WScript.Shell
    $DesktopPath = [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::Desktop)
    $ProgramsPath = [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::Programs)

    $PythonwCmd = (Get-Command pythonw -ErrorAction SilentlyContinue)
    $PythonCmd = (Get-Command python -ErrorAction SilentlyContinue)
    $TargetExe = if ($PythonwCmd) { $PythonwCmd.Source } elseif (Test-Path "C:\Python314\pythonw.exe") { "C:\Python314\pythonw.exe" } elseif ($PythonCmd) { $PythonCmd.Source } else { "pythonw.exe" }

    $MainPy = Join-Path $ScriptDir "main.py"
    $TargetArgs = "`"$MainPy`""

    # Acceso directo en Escritorio usando pythonw (100% nativo y libre de consola)
    $ShortcutDesktop = $WshShell.CreateShortcut((Join-Path $DesktopPath "Antigravity Bridge.lnk"))
    $ShortcutDesktop.TargetPath = $TargetExe
    $ShortcutDesktop.Arguments = $TargetArgs
    $ShortcutDesktop.WorkingDirectory = $ScriptDir
    $ShortcutDesktop.Description = "Antigravity Bridge - OpenAI Localhost Gateway"
    $ShortcutDesktop.Save()

    # Acceso directo en Menu Inicio
    $ShortcutStart = $WshShell.CreateShortcut((Join-Path $ProgramsPath "Antigravity Bridge.lnk"))
    $ShortcutStart.TargetPath = $TargetExe
    $ShortcutStart.Arguments = $TargetArgs
    $ShortcutStart.WorkingDirectory = $ScriptDir
    $ShortcutStart.Description = "Antigravity Bridge - OpenAI Localhost Gateway"
    $ShortcutStart.Save()

    Write-Host "  [OK] Acceso directo silencioso creado en el Escritorio." -ForegroundColor Green
    Write-Host "  [OK] Acceso directo silencioso creado en el Menu Inicio." -ForegroundColor Green
} catch {
    Write-Host "  [!] No se pudo crear acceso directo automatico: $_" -ForegroundColor DarkYellow
}

# 5. Lanzar la Aplicacion de forma limpia
Write-Host "[5/5] Instalacion completada con exito!" -ForegroundColor Cyan
Write-Host ""
if (-not $NoLaunch) {
    Write-Host "Iniciando Antigravity Bridge sin consola..." -ForegroundColor Green
    Start-Process -FilePath $TargetExe -ArgumentList $TargetArgs -WorkingDirectory $ScriptDir
    Write-Host "Listo. La aplicacion se encuentra abierta y lista para usar." -ForegroundColor Cyan
} else {
    Write-Host "Instalacion completada." -ForegroundColor Cyan
}
