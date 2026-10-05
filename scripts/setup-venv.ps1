<#
.SYNOPSIS
    依 requirements 建立／更新工具的隔離 venv。

.DESCRIPTION
    - 只用標準庫的工具 → 確保根目錄共用的 .venv 存在（只裝 requirements-dev.txt）
    - 有第三方依賴的工具 → 建 tools\<name>\.venv，裝 requirements-dev.txt + 工具自己的 requirements.txt
    裝完會跑一次依賴檢查，確認裝到的版本真的符合 requirements。

.EXAMPLE
    .\scripts\setup-venv.ps1 encrypter          # 建／更新一個工具的環境
    .\scripts\setup-venv.ps1 encrypter -Force   # 整個砍掉重建（換了版本範圍、環境髒掉時用）
    .\scripts\setup-venv.ps1 -All               # 全部工具
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string] $Tool,

    [switch] $All,
    [switch] $Force,

    # 建新 venv 用的 Python 版本（給 py launcher 用）
    [string] $PythonVersion = '3.11'
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\_common.ps1"


function New-Venv([string] $venvDir) {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) { Invoke-Native $py.Source @("-$PythonVersion", '-m', 'venv', $venvDir) "建立 venv" }
    else     { Invoke-Native 'python'   @('-m', 'venv', $venvDir) "建立 venv" }
}

function Initialize-Venv([string] $venvDir, [string[]] $reqFiles, [string] $label, [bool] $recreate) {
    if ($recreate -and (Test-Path $venvDir)) {
        Write-Host "    砍掉舊的 $label" -ForegroundColor Yellow
        Remove-Item $venvDir -Recurse -Force
    }
    $python = Join-Path $venvDir 'Scripts\python.exe'
    if (-not (Test-Path $python)) {
        Write-Host "    建立 $label (Python $PythonVersion)" -ForegroundColor DarkGray
        New-Venv $venvDir
    }
    $pipArgs = @('-m', 'pip', 'install', '--disable-pip-version-check', '-q')
    foreach ($r in $reqFiles) { $pipArgs += @('-r', $r) }
    Write-Host "    pip install $(($reqFiles | ForEach-Object { Split-Path $_ -Leaf }) -join ' + ')" -ForegroundColor DarkGray
    # requirements 檔是 UTF-8（含中文註解）。pip 預設用系統編碼讀檔，
    # 繁中 Windows 是 cp950 → UnicodeDecodeError。pip 這一步強制 UTF-8 模式。
    $prevUtf8 = $env:PYTHONUTF8
    $env:PYTHONUTF8 = '1'
    try { Invoke-Native $python $pipArgs "pip install ($label)" }
    finally { $env:PYTHONUTF8 = $prevUtf8 }
    $python
}

function Initialize-Tool([string] $name) {
    $toolDir = Get-ToolDir $name
    Write-Host ""
    Write-Host "==> $name" -ForegroundColor Cyan

    if ((Get-ToolDeps $toolDir).Count -gt 0) {
        $python = Initialize-Venv (Join-Path $toolDir '.venv') @($DevReqs, (Get-ToolRequirementsFile $toolDir)) "tools\$name\.venv" $Force
    }
    else {
        Write-Host "    只用標準庫 → 共用根目錄 .venv" -ForegroundColor DarkGray
        # 不因為某個工具 -Force 就把其他工具也在用的共用環境砍掉
        $python = Initialize-Venv (Join-Path $Root '.venv') @($DevReqs) '.venv (共用)' $false
    }

    Test-ToolDeps $name $python
    Write-Host "    OK -> $python" -ForegroundColor Green
}


$targets = @()
if ($All)      { $targets = Get-AllTools }
elseif ($Tool) { $targets = @($Tool) }
else {
    Write-Host "用法: .\scripts\setup-venv.ps1 <tool> [-Force] | -All [-Force]" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "可用的工具:" -ForegroundColor Cyan
    Get-AllTools | ForEach-Object { Write-Host "  - $_" }
    return
}

$failed = @()
foreach ($t in $targets) {
    try { Initialize-Tool $t }
    catch {
        $failed += $t
        Write-Host "    FAILED: $($_.Exception.Message)" -ForegroundColor Red
    }
}

Write-Host ""
if ($failed.Count -gt 0) {
    Write-Host "完成，但有 $($failed.Count) 個失敗: $($failed -join ', ')" -ForegroundColor Red
    exit 1
}
Write-Host "環境都就緒 ($($targets.Count) 個工具)" -ForegroundColor Green
