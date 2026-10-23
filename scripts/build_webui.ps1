# Build the new-UI preview: dist\DoDoClaw-preview\DoDoClaw.exe
# Usage:  powershell -ExecutionPolicy Bypass -File .\scripts\build_webui.ps1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root
$Py = Join-Path $Root ".venv\Scripts\python.exe"

& $Py -m pip install -q -e ".[webui]" "pyinstaller>=6.0"
$Dist = Join-Path $Root "dist\DoDoClaw-preview"
# Clear contents only (folder itself may be open in Explorer)
if (Test-Path $Dist) { Get-ChildItem $Dist -Force | Remove-Item -Recurse -Force }

& $Py -m PyInstaller --noconfirm --clean --workpath "$Root\build" "$Root\packaging\dodoclaw_webui.spec"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
# build\ only holds intermediates; its exe cannot run, so don't leave it around
if (Test-Path "$Root\build") { Remove-Item -Recurse -Force "$Root\build" }

$Exe = Join-Path $Dist "DoDoClaw.exe"
if (-not (Test-Path $Exe)) { throw "exe not found" }
Copy-Item -Force "$Root\.env.example" "$Dist\.env.example" -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force "$Dist\config" | Out-Null
Copy-Item -Force "$Root\config\*" "$Dist\config\" -ErrorAction SilentlyContinue
Write-Host "Build OK: $Exe" -ForegroundColor Green
