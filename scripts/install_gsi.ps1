# Install DoDoClaw GSI cfg into Dota 2
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Src = Join-Path $Root "config\gamestate_integration_dodoclaw.cfg"

$Candidates = @(
    "${env:ProgramFiles(x86)}\Steam\steamapps\common\dota 2 beta\game\dota\cfg\gamestate_integration",
    "C:\Program Files (x86)\Steam\steamapps\common\dota 2 beta\game\dota\cfg\gamestate_integration",
    "D:\Steam\steamapps\common\dota 2 beta\game\dota\cfg\gamestate_integration",
    "E:\Steam\steamapps\common\dota 2 beta\game\dota\cfg\gamestate_integration"
)

if ($env:STEAM_PATH) {
    $Candidates = @(
        (Join-Path $env:STEAM_PATH "steamapps\common\dota 2 beta\game\dota\cfg\gamestate_integration")
    ) + $Candidates
}

$TargetDir = $null
foreach ($c in $Candidates) {
    $parent = Split-Path -Parent $c
    if (Test-Path $parent) {
        $TargetDir = $c
        break
    }
}

if (-not $TargetDir) {
    Write-Host "未找到 Dota 2 目录。请设置 STEAM_PATH 或手动复制:" -ForegroundColor Yellow
    Write-Host "  $Src"
    Write-Host '到 <Steam>\steamapps\common\dota 2 beta\game\dota\cfg\gamestate_integration\'
    exit 2
}

New-Item -ItemType Directory -Force -Path $TargetDir | Out-Null
$Dest = Join-Path $TargetDir "gamestate_integration_dodoclaw.cfg"
Copy-Item -Force $Src $Dest
Write-Host "已安装: $Dest" -ForegroundColor Green
Write-Host "请完全重启 Dota 2 后再进对局。"
