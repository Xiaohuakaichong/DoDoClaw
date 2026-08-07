# Launch the packaged desktop app (dist folder — NOT build/)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Exe = Join-Path $Root "dist\DoDoClaw\DoDoClaw.exe"

if (-not (Test-Path $Exe)) {
    Write-Host "未找到: $Exe" -ForegroundColor Red
    Write-Host "请先打包: powershell -ExecutionPolicy Bypass -File .\scripts\build_app.ps1"
    exit 1
}

Write-Host "启动: $Exe" -ForegroundColor Green
Write-Host "提示: 不要运行 build\dodoclaw\DoDoClaw.exe（那是中间产物，会缺 DLL）"
Start-Process -FilePath $Exe -WorkingDirectory (Split-Path $Exe)
