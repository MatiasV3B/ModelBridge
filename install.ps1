<#
.SYNOPSIS
    Instalador de Antigravity Bridge para Windows (basado en uv, sin tocar el Python del sistema).
.DESCRIPTION
    0. Si se ejecuta fuera del repo (irm ... | iex), descarga el Bridge a %LOCALAPPDATA%\AntigravityBridge.
    1. Verifica e instala el CLI de Antigravity (agy).
    2. Instala uv (si falta) y crea un entorno aislado .venv con su propio Python y las dependencias.
    3. Comprueba el estado de inicio de sesion de Antigravity.
    4. Crea accesos directos silenciosos en el Escritorio y en el Menu Inicio.
    5. Inicia la aplicacion sin ventanas de terminal.

    Instalacion en un solo comando:
        irm https://raw.githubusercontent.com/MatiasV3B/ModelBridge/main/install.ps1 | iex
    Para actualizar mas tarde: Actualizar-AntigravityBridge.bat (o update.ps1).
#>

param(
    [switch]$NoLaunch
)

$ErrorActionPreference = "Stop"
$RepoZip = "https://github.com/MatiasV3B/ModelBridge/archive/refs/heads/main.zip"

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "      ANTIGRAVITY BRIDGE PARA WINDOWS - INSTALADOR      " -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

# 0. Ubicar el proyecto (o descargarlo si se ejecuto con irm | iex)
$ScriptDir = $null
if ($MyInvocation.MyCommand.Path) { $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path }

if (-not $ScriptDir -or -not (Test-Path (Join-Path $ScriptDir "main.py"))) {
    $ScriptDir = Join-Path $env:LOCALAPPDATA "AntigravityBridge"
    Write-Host "[0/5] Descargando Antigravity Bridge en $ScriptDir ..." -ForegroundColor Yellow
    $TmpZip = Join-Path $env:TEMP "AntigravityBridge-main.zip"
    $TmpDir = Join-Path $env:TEMP "AntigravityBridge-extract"
    Invoke-WebRequest -Uri $RepoZip -OutFile $TmpZip -UseBasicParsing
    if (Test-Path $TmpDir) { Remove-Item $TmpDir -Recurse -Force }
    Expand-Archive -Path $TmpZip -DestinationPath $TmpDir -Force
    $Extracted = Get-ChildItem $TmpDir -Directory | Select-Object -First 1
    New-Item -ItemType Directory -Force -Path $ScriptDir | Out-Null
    & robocopy $Extracted.FullName $ScriptDir /E /XD .venv .git /XF .env /NFL /NDL /NJH /NJS /NP | Out-Null
    Remove-Item $TmpZip, $TmpDir -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "  [OK] Descarga completada." -ForegroundColor Green
}
Set-Location $ScriptDir

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

# 2. Entorno aislado con uv (descarga su propio Python; no usa ni modifica el Python del sistema)
Write-Host "[2/5] Preparando entorno aislado (uv)..." -ForegroundColor Yellow

function Find-Uv {
    $cmd = Get-Command uv -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach ($p in @((Join-Path $env:USERPROFILE ".local\bin\uv.exe"), (Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Links\uv.exe"))) {
        if (Test-Path $p) { return $p }
    }
    return $null
}

$Uv = Find-Uv
if (-not $Uv) {
    Write-Host "  [..] Instalando uv (gestor de entornos, un solo binario)..." -ForegroundColor Cyan
    try {
        irm https://astral.sh/uv/install.ps1 | iex
    } catch {
        Write-Host "  [!] Fallo el instalador oficial de uv: $_" -ForegroundColor DarkYellow
    }
    $env:Path = (Join-Path $env:USERPROFILE ".local\bin") + ";" + $env:Path
    $Uv = Find-Uv
}
if (-not $Uv) {
    Write-Host "  [!] No se pudo instalar uv. Instalalo manualmente: winget install --id astral-sh.uv -e" -ForegroundColor Red
    pause
    exit 1
}

function Find-SystemPython {
    # Python ya instalado (no el alias vacio de la Microsoft Store). Solo se usa como base si uv no puede usar el suyo.
    $candidates = @()
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        $exe = & $py.Source -3 -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $exe) { $candidates += $exe }
    }
    $pc = Get-Command python -ErrorAction SilentlyContinue
    if ($pc -and $pc.Source -notlike "*\WindowsApps\*") { $candidates += $pc.Source }
    foreach ($c in $candidates) {
        $ver = & $c -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        if ($LASTEXITCODE -eq 0 -and $ver -and ([version]$ver -ge [version]"3.10")) { return $c }
    }
    return $null
}

Write-Host "  -> Creando .venv e instalando dependencias..." -ForegroundColor Gray
$SyncArgs = @("sync")
if (Test-Path (Join-Path $ScriptDir "uv.lock")) { $SyncArgs += "--frozen" }
& $Uv @SyncArgs
if ($LASTEXITCODE -ne 0) {
    # Ej.: una politica de Windows (Control de aplicaciones / Smart App Control) puede bloquear el Python que descarga uv
    Write-Host "  [!] uv no pudo usar su propio Python. Probando con el Python instalado en el sistema..." -ForegroundColor DarkYellow
    $SysPy = Find-SystemPython
    if ($SysPy) {
        if (Test-Path (Join-Path $ScriptDir ".venv")) { Remove-Item (Join-Path $ScriptDir ".venv") -Recurse -Force -ErrorAction SilentlyContinue }
        & $Uv @SyncArgs --python $SysPy
    }
}
if ($LASTEXITCODE -ne 0 -or -not (Test-Path (Join-Path $ScriptDir ".venv\Scripts\pythonw.exe"))) {
    Write-Host "  [!] No se pudo crear el entorno. Revisa tu conexion o instala Python 3.10+ desde python.org y vuelve a intentar." -ForegroundColor Red
    pause
    exit 1
}
Write-Host "  [OK] Entorno listo en $ScriptDir\.venv" -ForegroundColor Green

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
$TargetExe = Join-Path $ScriptDir ".venv\Scripts\pythonw.exe"
$MainPy = Join-Path $ScriptDir "main.py"
$TargetArgs = "`"$MainPy`""
try {
    $WshShell = New-Object -ComObject WScript.Shell
    $DesktopPath = [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::Desktop)
    $ProgramsPath = [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::Programs)

    foreach ($dir in @($DesktopPath, $ProgramsPath)) {
        $lnk = $WshShell.CreateShortcut((Join-Path $dir "Antigravity Bridge.lnk"))
        $lnk.TargetPath = $TargetExe
        $lnk.Arguments = $TargetArgs
        $lnk.WorkingDirectory = $ScriptDir
        $lnk.Description = "Antigravity Bridge - OpenAI Localhost Gateway"
        $lnk.Save()
    }
    Write-Host "  [OK] Accesos directos creados (Escritorio y Menu Inicio)." -ForegroundColor Green
} catch {
    Write-Host "  [!] No se pudo crear acceso directo automatico: $_" -ForegroundColor DarkYellow
}

# 5. Lanzar la Aplicacion de forma limpia
Write-Host "[5/5] Instalacion completada con exito!" -ForegroundColor Cyan
Write-Host ""
if (-not $NoLaunch) {
    Write-Host "Iniciando Antigravity Bridge sin consola..." -ForegroundColor Green
    Start-Process -FilePath $TargetExe -ArgumentList $TargetArgs -WorkingDirectory $ScriptDir
    Write-Host "Listo. Para actualizar mas adelante usa Actualizar-AntigravityBridge.bat" -ForegroundColor Cyan
} else {
    Write-Host "Instalacion completada." -ForegroundColor Cyan
}
