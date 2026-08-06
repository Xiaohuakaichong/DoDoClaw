# Build portable DoDoClaw Windows app (folder + exe)
# Usage:  powershell -ExecutionPolicy Bypass -File .\scripts\build_app.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

Write-Host "==> DoDoClaw desktop build" -ForegroundColor Cyan
Write-Host "Root: $Root"

$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) {
    Write-Host "Creating venv..." -ForegroundColor Yellow
    python -m venv .venv
    $Py = Join-Path $Root ".venv\Scripts\python.exe"
}

& $Py -m pip install -U pip wheel
& $Py -m pip install -e ".[app,dev]"
& $Py -m pip install "pyinstaller>=6.0"

# Clean previous build
if (Test-Path "$Root\build") { Remove-Item -Recurse -Force "$Root\build" }
if (Test-Path "$Root\dist\DoDoClaw") { Remove-Item -Recurse -Force "$Root\dist\DoDoClaw" }

Write-Host "==> Running PyInstaller..." -ForegroundColor Cyan
& $Py -m PyInstaller --noconfirm --clean "$Root\packaging\dodoclaw.spec"

$Exe = Join-Path $Root "dist\DoDoClaw\DoDoClaw.exe"
if (-not (Test-Path $Exe)) {
    Write-Host "Build failed: exe not found" -ForegroundColor Red
    exit 1
}

# Seed portable files next to exe if missing
$Dist = Join-Path $Root "dist\DoDoClaw"
Copy-Item -Force "$Root\.env.example" "$Dist\.env.example" -ErrorAction SilentlyContinue
if (-not (Test-Path "$Dist\config")) {
    New-Item -ItemType Directory -Path "$Dist\config" | Out-Null
}
Copy-Item -Force "$Root\config\*" "$Dist\config\" -ErrorAction SilentlyContinue

# Zip for community release
$Zip = Join-Path $Root "dist\DoDoClaw-win64.zip"
if (Test-Path $Zip) { Remove-Item -Force $Zip }
Compress-Archive -Path "$Dist\*" -DestinationPath $Zip -Force

Write-Host ""
Write-Host "Build OK" -ForegroundColor Green
Write-Host "  EXE : $Exe"
Write-Host "  ZIP : $Zip"
Write-Host ""
Write-Host "Community tips:" -ForegroundColor Cyan
Write-Host "  1. Share DoDoClaw-win64.zip"
Write-Host "  2. Users unzip -> run DoDoClaw.exe"
Write-Host "  3. Fill API Key in UI -> Install GSI -> Start"
