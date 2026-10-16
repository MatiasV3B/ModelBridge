<#
.SYNOPSIS
    Instalador de Antigravity Bridge para Windows (modo seguro con uv o modo normal con pip).
.DESCRIPTION
    0. Si se ejecuta fuera del repo (irm ... | iex), descarga el Bridge a %LOCALAPPDATA%\AntigravityBridge.
    1. Verifica e instala el CLI de Antigravity (agy).
    2. Prepara Python segun el modo de instalacion:
         seguro (recomendado): instala uv (si falta) y crea un entorno aislado .venv con su propio Python y las
                               dependencias. No toca ni depende del Python del sistema.
         normal:               instala las dependencias con pip (--user) en el Python que ya tienes instalado.
                               Mas simple, pero mezcla paquetes con los de tu Python.
    3. Comprueba el estado de inicio de sesion de Antigravity.
    4. Crea accesos directos silenciosos en el Escritorio y en el Menu Inicio.
    5. Inicia la aplicacion sin ventanas de terminal.

    El modo se elige asi (el primero que exista):  -Mode secure|normal  >  variable BRIDGE_INSTALL_MODE  >
    el modo guardado en .install-mode  >  pregunta en pantalla (solo en una instalacion normal)  >  seguro.

    Instalacion en un solo comando (modo seguro por defecto):
        irm https://raw.githubusercontent.com/MatiasV3B/ModelBridge/main/install.ps1 | iex
    Modo normal en un solo comando:
        $env:BRIDGE_INSTALL_MODE = 'normal'; irm https://raw.githubusercontent.com/MatiasV3B/ModelBridge/main/install.ps1 | iex
    Para actualizar mas tarde: Actualizar-AntigravityBridge.bat (o update.ps1); conserva el modo elegido.
#>

param(
    [switch]$NoLaunch,
    [ValidateSet('secure', 'normal')]
    [string]$Mode
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

$ModeFile = Join-Path $ScriptDir ".install-mode"
$PythonFile = Join-Path $ScriptDir ".python-path"

function Resolve-InstallMode {
    foreach ($m in @($Mode, $env:BRIDGE_INSTALL_MODE)) {
        if ($m -in @('secure', 'normal')) { return $m }
    }
    if (Test-Path $ModeFile) {
        $saved = (Get-Content $ModeFile -Raw).Trim()
        if ($saved -in @('secure', 'normal')) { return $saved }
    }
    # Solo se pregunta en una instalacion interactiva; las llamadas con -NoLaunch (actualizar, primer inicio) no preguntan.
    if (-not $NoLaunch -and [Environment]::UserInteractive) {
        Write-Host "Como quieres instalarlo?" -ForegroundColor Cyan
        Write-Host "  [1] Modo seguro (recomendado): entorno aislado (.venv con uv). No toca tu Python ni sus paquetes."
        Write-Host "  [2] Modo normal: usa pip con el Python de tu sistema (--user). Mas simple, pero mezcla paquetes con los tuyos."
        try {
            $answer = Read-Host "Elige 1 o 2 [1]"
            if ($answer.Trim() -in @('2', 'normal', 'n')) { return 'normal' }
        } catch { }
    }
    return 'secure'
}

$InstallMode = Resolve-InstallMode
Write-Host "Modo de instalacion: $InstallMode" -ForegroundColor Cyan
Write-Host ""

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

function Find-Uv {
    $cmd = Get-Command uv -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach ($p in @((Join-Path $env:USERPROFILE ".local\bin\uv.exe"), (Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Links\uv.exe"))) {
        if (Test-Path $p) { return $p }
    }
    return $null
}

function Find-SystemPython {
    # Python ya instalado (no el alias vacio de la Microsoft Store). En modo normal es el que se usa;
    # en modo seguro solo es el plan B si uv no puede usar el suyo.
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

# 2. Python y dependencias segun el modo
if ($InstallMode -eq 'normal') {
    Write-Host "[2/5] Instalando dependencias con pip en tu Python (modo normal)..." -ForegroundColor Yellow
    Write-Host "  [!] Esto agrega paquetes (fastapi, pydantic, pillow...) al Python de tu usuario y puede cambiar versiones que ya tengas." -ForegroundColor DarkYellow
    Write-Host "      Si prefieres no tocarlo, vuelve a instalar en modo seguro." -ForegroundColor DarkYellow

    $SysPy = Find-SystemPython
    if (-not $SysPy) {
        Write-Host "  [!] No se encontro Python 3.10 o superior. Instalalo (winget install --id Python.Python.3.12 -e) o usa el modo seguro." -ForegroundColor Red
        pause
        exit 1
    }
    Write-Host "  -> Usando $SysPy" -ForegroundColor Gray
    & $SysPy -m pip install --user --disable-pip-version-check -r (Join-Path $ScriptDir "requirements.txt")
    if ($LASTEXITCODE -eq 0) {
        & $SysPy -c "import fastapi, uvicorn, customtkinter, pydantic, PIL, requests" 2>$null
    }
    $Pythonw = Join-Path (Split-Path -Parent $SysPy) "pythonw.exe"
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $Pythonw)) {
        Write-Host "  [!] No se pudieron instalar las dependencias con pip. Revisa tu conexion o usa el modo seguro." -ForegroundColor Red
        pause
        exit 1
    }
    # Ruta corta (8.3, solo ASCII) para que los .bat y .vbs la lean sin problemas de codificacion
    try { $Pythonw = (New-Object -ComObject Scripting.FileSystemObject).GetFile($Pythonw).ShortPath } catch { }
    if ($Pythonw -match '[^\x00-\x7F]') {
        Write-Host "  [!] La ruta de Python tiene caracteres especiales; los accesos pueden fallar. Si pasa, usa el modo seguro." -ForegroundColor DarkYellow
    }
    [System.IO.File]::WriteAllText($PythonFile, $Pythonw, [System.Text.Encoding]::ASCII)
    $TargetExe = $Pythonw
    Write-Host "  [OK] Dependencias instaladas en $SysPy" -ForegroundColor Green
} else {
    # Entorno aislado con uv (descarga su propio Python; no usa ni modifica el Python del sistema)
    Write-Host "[2/5] Preparando entorno aislado (uv)..." -ForegroundColor Yellow

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
    # El modo seguro siempre usa el .venv: se borra la ruta de un modo normal anterior
    Remove-Item $PythonFile -Force -ErrorAction SilentlyContinue
    $TargetExe = Join-Path $ScriptDir ".venv\Scripts\pythonw.exe"
    Write-Host "  [OK] Entorno listo en $ScriptDir\.venv" -ForegroundColor Green
}
[System.IO.File]::WriteAllText($ModeFile, $InstallMode, [System.Text.Encoding]::ASCII)

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
Write-Host "[5/5] Instalacion completada con exito! (modo $InstallMode)" -ForegroundColor Cyan
Write-Host ""
if (-not $NoLaunch) {
    Write-Host "Iniciando Antigravity Bridge sin consola..." -ForegroundColor Green
    Start-Process -FilePath $TargetExe -ArgumentList $TargetArgs -WorkingDirectory $ScriptDir
    Write-Host "Listo. Para actualizar mas adelante usa Actualizar-AntigravityBridge.bat" -ForegroundColor Cyan
} else {
    Write-Host "Instalacion completada." -ForegroundColor Cyan
}
