<#
.SYNOPSIS
    改一個工具的版本號（只改檔案，不 build、不 commit）。

.DESCRIPTION
    版本號唯一的來源是 tool.json 的 version_from 指到的檔案裡的 __version__。
    改完之後 build 出來的 exe 檔名、程式視窗標題都會自動跟著變。
    要「改版號 + build + commit + 打 tag」一次做完，用 release.ps1。

.EXAMPLE
    .\scripts\bump-version.ps1                  # 選單
    .\scripts\bump-version.ps1 hash patch       # 0.1.0 → 0.1.1
    .\scripts\bump-version.ps1 hash minor       # 0.1.0 → 0.2.0
    .\scripts\bump-version.ps1 hash major       # 0.1.0 → 1.0.0
    .\scripts\bump-version.ps1 hash 2.3.4       # 直接指定
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ArgumentCompleter({
        param($cmd, $param, $word)
        $base = try { Split-Path -Parent (Split-Path -Parent (Resolve-Path $cmd -ErrorAction Stop).Path) } catch { (Get-Location).Path }
        Get-ChildItem (Join-Path $base 'tools') -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -notlike '_*' -and $_.Name -like "$word*" } | ForEach-Object { $_.Name }
    })]
    [string] $Tool,

    [Parameter(Position = 1)]
    [ArgumentCompleter({ param($c, $p, $w) 'patch', 'minor', 'major' | Where-Object { $_ -like "$w*" } })]
    [string] $Bump
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\_common.ps1"

$name = @(Resolve-ToolTargets @($Tool) '改版本號' $false)
if ($name.Count -eq 0) { Write-Host "沒有選工具，結束。" -ForegroundColor Yellow; return }
$info = Get-ToolInfo $name[0]

if (-not $Bump) {
    $Bump = Read-BumpChoice $info.Version
    if (-not $Bump) { Write-Host "沒有選，結束。" -ForegroundColor Yellow; return }
}
$new = Get-BumpedVersion $info.Version $Bump

Set-ToolVersion $info $new
$rel = $info.VersionFile.Substring($Root.Length + 1)
Write-Host "$($info.Name): $($info.Version) → $new   ($rel)" -ForegroundColor Green
Write-Host "下一步: .\scripts\build.ps1 $($info.Name)   → dist\$($info.Name)\$($info.Config.name)(v$new).exe"
