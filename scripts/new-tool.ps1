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

Get-ChildItem $Target -Recurse -File | ForEach-Object {
    $content = Get-Content $_.FullName -Raw -Encoding UTF8
    if ($content -match '__TOOL_NAME__') {
        ($content -replace '__TOOL_NAME__', $Name) |
            Set-Content $_.FullName -Encoding UTF8 -NoNewline
    }
}

Write-Host ""
Write-Host "建好了: tools\$Name" -ForegroundColor Green
Write-Host ""
Write-Host "接下來:" -ForegroundColor Cyan
Write-Host "  1. 寫 tools\$Name\main.py"
Write-Host "  2. 有資料檔就填 tools\$Name\tool.json 的 include"
Write-Host "  3. .\scripts\build.ps1 $Name"
Write-Host "  4. 在根目錄 README.md 的工具表格加一列"
