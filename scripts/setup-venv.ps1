<#
.SYNOPSIS
    依 requirements 建立／更新工具的隔離 venv。

.DESCRIPTION
    平常不用手動跑：build.ps1 發現環境不存在或版本不符會自動處理。
    這支是給「想直接跑原始碼開發」或「想整個砍掉重建」的時候用。

    - 只用標準庫的工具 → 根目錄共用的 .venv（只裝 requirements-dev.txt）
    - 有第三方依賴的工具 → tools\<name>\.venv（requirements-dev.txt + 工具自己的 requirements.txt）
    裝完會跑一次依賴檢查，確認裝到的版本真的符合 requirements。

.EXAMPLE
    .\scripts\setup-venv.ps1                    # 選單
    .\scripts\setup-venv.ps1 encrypter          # 建／更新一個工具的環境（名稱可打不完整）
    .\scripts\setup-venv.ps1 enc -Force         # 整個砍掉重建
    .\scripts\setup-venv.ps1 -All
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
    [ArgumentCompleter({
        param($cmd, $param, $word)
        $base = try { Split-Path -Parent (Split-Path -Parent (Resolve-Path $cmd -ErrorAction Stop).Path) } catch { (Get-Location).Path }
        Get-ChildItem (Join-Path $base 'tools') -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -notlike '_*' -and $_.Name -like "$word*" } | ForEach-Object { $_.Name }
    })]
    [string[]] $Tool,

    [switch] $All,
    [switch] $Force,

    # 建新 venv 用的 Python 版本（給 py launcher 用）
    [string] $PythonVersion = '3.11'
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\_common.ps1"

$targets = if ($All) { Get-AllTools } else { Resolve-ToolTargets $Tool '建立環境' $true }
if ($targets.Count -eq 0) {
    Write-Host "沒有選任何工具，結束。用法: .\scripts\setup-venv.ps1 [工具名稱...] [-All] [-Force]" -ForegroundColor Yellow
    return
}

$failed = @()
foreach ($t in $targets) {
    Write-Host ""
    Write-Host "==> $t" -ForegroundColor Cyan
    try {
        $info = Get-ToolInfo $t
        if (-not $info.HasDeps) { Write-Host "    只用標準庫 → 共用根目錄 .venv" -ForegroundColor DarkGray }
        Initialize-ToolEnv $info ([bool] $Force) $PythonVersion
        Test-ToolDeps $info $info.Python $false
        Write-Host "    OK -> $($info.Python)" -ForegroundColor Green
    }
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
