<#
.SYNOPSIS
    從 tools\_template 生一個新工具骨架。

.EXAMPLE
    .\scripts\new-tool.ps1 my-new-tool
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string] $Name
)

$ErrorActionPreference = 'Stop'

$Root     = Split-Path -Parent $PSScriptRoot
$Template = Join-Path $Root 'tools\_template'
$Target   = Join-Path $Root "tools\$Name"

if ($Name -notmatch '^[a-z0-9]+(-[a-z0-9]+)*$') {
    throw "工具名稱請用小寫 kebab-case（例如 my-new-tool），收到的是: $Name"
}
if (Test-Path $Target) { throw "tools\$Name 已經存在了" }
if (-not (Test-Path $Template)) { throw "找不到 tools\_template" }

Copy-Item $Template $Target -Recurse

# 用無 BOM 的 UTF-8 寫回（Windows PowerShell 5.1 的 Set-Content -Encoding UTF8 會加 BOM）
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
Get-ChildItem $Target -Recurse -File | ForEach-Object {
    $content = [System.IO.File]::ReadAllText($_.FullName, $utf8NoBom)
    if ($content.Contains('__TOOL_NAME__')) {
        [System.IO.File]::WriteAllText($_.FullName, $content.Replace('__TOOL_NAME__', $Name), $utf8NoBom)
    }
}

Write-Host ""
Write-Host "建好了: tools\$Name" -ForegroundColor Green
Write-Host ""
Write-Host "接下來:" -ForegroundColor Cyan
Write-Host "  1. 寫 tools\$Name\main.py（版本號在 version.py）"
Write-Host "  2. 需要第三方套件就寫進 tools\$Name\requirements.txt（記得給主版本上限，例如 pandas>=2.0,<3）"
Write-Host "  3. .\scripts\setup-venv.ps1 $Name      # 有第三方套件會建專屬 .venv，沒有就用共用的"
Write-Host "  4. 有資料檔就填 tools\$Name\tool.json 的 include"
Write-Host "  5. .\scripts\build.ps1 $Name"
Write-Host "  6. 在根目錄 README.md 的工具表格加一列"
