<#
.SYNOPSIS
    PersonalToolZoo 統一 builder。

.DESCRIPTION
    所有工具共用 scripts\tool.spec，各工具的差異只寫在 tools\<name>\tool.json。
    所有路徑都以「工具資料夾」為基準解析，所以你站在哪個目錄下執行結果都一樣。

.EXAMPLE
    .\scripts\build.ps1 git-helper-pro     # build 單一工具
    .\scripts\build.ps1 -All               # build 全部
    .\scripts\build.ps1 -List              # 列出有哪些工具
    .\scripts\build.ps1 -Clean             # 清掉 build\ 與 dist\
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string] $Tool,

    [switch] $All,
    [switch] $List,
    [switch] $Clean
)

$ErrorActionPreference = 'Stop'

$Root     = Split-Path -Parent $PSScriptRoot
$ToolsDir = Join-Path $Root 'tools'
$Spec     = Join-Path $PSScriptRoot 'tool.spec'


function Get-AllTools {
    if (-not (Test-Path $ToolsDir)) { return @() }
    Get-ChildItem -Path $ToolsDir -Directory |
        Where-Object { $_.Name -notlike '_*' } |
        Where-Object { Test-Path (Join-Path $_.FullName 'tool.json') } |
        Select-Object -ExpandProperty Name
}

function Resolve-Python([string] $toolDir) {
    # 優先用工具自己的 .venv（某個工具依賴衝突時可單獨開一個），否則用根目錄共用的
    foreach ($c in @(
        (Join-Path $toolDir '.venv\Scripts\python.exe'),
        (Join-Path $Root    '.venv\Scripts\python.exe')
    )) {
        if (Test-Path $c) { return $c }
    }
    throw @"
找不到 python.exe。請先在 repo 根目錄建立共用環境：
    py -3.11 -m venv .venv
    .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
"@
}

function Build-Tool([string] $name) {
    $toolDir = Join-Path $ToolsDir $name
    if (-not (Test-Path (Join-Path $toolDir 'tool.json'))) {
        throw "tools\$name\tool.json 不存在 —— 用 .\scripts\build.ps1 -List 看有哪些工具"
    }

    $python   = Resolve-Python $toolDir
    $distPath = Join-Path $Root "dist\$name"
    $workPath = Join-Path $Root "build\$name"

    Write-Host ""
    Write-Host "==> building $name" -ForegroundColor Cyan
    Write-Host "    python: $python" -ForegroundColor DarkGray

    $env:TOOLZOO_TOOL_DIR = $toolDir
    try {
        & $python -m PyInstaller $Spec --noconfirm --distpath $distPath --workpath $workPath
        if ($LASTEXITCODE -ne 0) { throw "build $name 失敗 (exit code $LASTEXITCODE)" }
    }
    finally {
        $env:TOOLZOO_TOOL_DIR = $null
    }

    Get-ChildItem -Path $distPath -Filter *.exe | ForEach-Object {
        $mb = [math]::Round($_.Length / 1MB, 1)
        Write-Host "    OK -> dist\$name\$($_.Name)  ($mb MB)" -ForegroundColor Green
    }
}


# ---------------------------------------------------------------- main
if ($Clean) {
    foreach ($d in @('build', 'dist')) {
        $p = Join-Path $Root $d
        if (Test-Path $p) {
            Remove-Item $p -Recurse -Force
            Write-Host "removed $d\" -ForegroundColor Yellow
        }
    }
    if (-not $Tool -and -not $All) { return }
}

if ($List) {
    Write-Host "tools/:" -ForegroundColor Cyan
    Get-AllTools | ForEach-Object { Write-Host "  - $_" }
    return
}

$targets = @()
if ($All)        { $targets = Get-AllTools }
elseif ($Tool)   { $targets = @($Tool) }
else {
    Write-Host "用法: .\scripts\build.ps1 <tool> | -All | -List | -Clean" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "可用的工具:" -ForegroundColor Cyan
    Get-AllTools | ForEach-Object { Write-Host "  - $_" }
    return
}

if ($targets.Count -eq 0) { throw "沒有可以 build 的工具" }

$failed = @()
foreach ($t in $targets) {
    try { Build-Tool $t }
    catch {
        $failed += $t
        Write-Host "    FAILED: $($_.Exception.Message)" -ForegroundColor Red
        if ($targets.Count -eq 1) { throw }
    }
}

Write-Host ""
if ($failed.Count -gt 0) {
    Write-Host "完成，但有 $($failed.Count) 個失敗: $($failed -join ', ')" -ForegroundColor Red
    exit 1
}
Write-Host "全部完成 ($($targets.Count) 個工具)" -ForegroundColor Green
