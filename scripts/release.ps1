<#
.SYNOPSIS
    發布一個工具：改版號 → 清快取從頭 build → 冒煙測試 → commit 版本檔 → 打 tag。

.DESCRIPTION
    任何一步失敗都會把版本檔還原，不會留下改了一半的狀態。
    不會自動 push，最後會印出 push 指令讓你自己決定。

    事前檢查（不通過就不動任何東西）：
      - 這個工具資料夾、以及 tool.json 的 pathex 指到的共用程式碼（例如 libs/），
        都不能有還沒 commit 的修改（release 必須對應到已 commit 的程式碼）
      - 不能有已經 git add 但還沒 commit 的東西（避免被一起 commit 進去）
      - 新的 tag 不能已經存在

.EXAMPLE
    .\scripts\release.ps1                       # 選單：選工具 → 選怎麼改版號 → 確認
    .\scripts\release.ps1 hash patch            # HashMyFile 0.1.0 → 0.1.1 並發布
    .\scripts\release.ps1 hash 1.0.0            # 直接指定版本
    .\scripts\release.ps1 hash keep             # 不改版本，發布目前版本（例如補打漏掉的 tag）
    .\scripts\release.ps1 hash patch -NoTag     # 不打 tag
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
    [ArgumentCompleter({ param($c, $p, $w) 'patch', 'minor', 'major', 'keep' | Where-Object { $_ -like "$w*" } })]
    [string] $Bump,

    [switch] $NoTag,
    # 不問確認（給自動化用）
    [switch] $Yes
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\_common.ps1"

function Invoke-Git([string[]] $gitArgs) {
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { $out = & git -C $Root @gitArgs 2>&1 | ForEach-Object { "$_" } }
    finally { $ErrorActionPreference = $prev }
    if ($LASTEXITCODE -ne 0) { throw "git $($gitArgs -join ' ') 失敗:`n$($out -join "`n")" }
    $out
}

# ---------------------------------------------------------------- 選工具、選版本
$name = @(Resolve-ToolTargets @($Tool) '發布' $false)
if ($name.Count -eq 0) { Write-Host "沒有選工具，結束。" -ForegroundColor Yellow; return }
$info = Get-ToolInfo $name[0]
$interactive = -not $Tool -or -not $Bump

if (-not $Bump) {
    $Bump = Read-BumpChoice $info.Version $true
    if (-not $Bump) { Write-Host "沒有選，結束。" -ForegroundColor Yellow; return }
}
$keep = ($Bump -eq 'keep')
$new  = if ($keep) { $info.Version } else { Get-BumpedVersion $info.Version $Bump }
$tag  = "$($info.TagPrefix)_v$new"
$versionRel = $info.VersionFile.Substring($Root.Length + 1).Replace('\', '/')
$sources    = @($info.SourcePaths)   # 工具資料夾 + tool.json 的 pathex（例如共用的 libs/）

# ---------------------------------------------------------------- 事前檢查
$dirty = @(Invoke-Git (@('status', '--porcelain', '--') + $sources))
if ($dirty.Count -gt 0) {
    throw "$($sources -join '、') 裡有還沒 commit 的修改（都會被打包進 exe），先 commit 再發布：`n$($dirty -join "`n")"
}
$staged = @(Invoke-Git @('diff', '--cached', '--name-only'))
if ($staged.Count -gt 0) {
    throw "有已經 git add 但還沒 commit 的檔案，會被一起 commit 進 release，先處理掉：`n$($staged -join "`n")"
}
if (-not $NoTag -and @(Invoke-Git @('tag', '--list', $tag)).Count -gt 0) {
    throw "tag $tag 已經存在。要發新版本請改版號（patch / minor / major）"
}
if ($keep -and $NoTag) { throw "keep + -NoTag 等於什麼都不做；只想 build 請用 build.ps1" }

# ---------------------------------------------------------------- 確認
$branch = (Invoke-Git @('rev-parse', '--abbrev-ref', 'HEAD')) -join ''
Write-Host ""
Write-Host "================ release" -ForegroundColor Cyan
Write-Host "  工具   : $($info.Name)"
Write-Host "  版本   : v$($info.Version) → v$new$(if ($keep) { '（不變）' })"
Write-Host "  產物   : dist\$($info.Name)\$($info.Config.name)(v$new).exe"
Write-Host "  commit : $(if ($keep) { '（版本沒變，不 commit）' } else { "release($($info.Name)): v$new  → 分支 $branch" })"
Write-Host "  tag    : $(if ($NoTag) { '（不打）' } else { $tag })"
if (($interactive -or -not $Yes) -and -not (Confirm-YesNo "開始？" $true)) { Write-Host "取消。" -ForegroundColor Yellow; return }

# ---------------------------------------------------------------- 改版號 + build
if (-not $keep) {
    Set-ToolVersion $info $new
    Write-Host "  改版號: $versionRel → $new" -ForegroundColor DarkGray
}
try {
    $global:LASTEXITCODE = 0
    & (Join-Path $PSScriptRoot 'build.ps1') -Tool $info.Name -Clean | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "build 或冒煙測試失敗" }

    if (-not $keep) {
        Invoke-Git @('add', '--', $versionRel) | Out-Null
        Invoke-Git @('commit', '-q', '-m', "release($($info.Name)): v$new", '--', $versionRel) | Out-Null
    }
}
catch {
    if (-not $keep) {
        Invoke-Git @('restore', '--staged', '--worktree', '--', $versionRel) | Out-Null
        Write-Host "  已把 $versionRel 還原回 v$($info.Version)" -ForegroundColor Yellow
    }
    throw "release 中止: $($_.Exception.Message)"
}

if (-not $NoTag) {
    Invoke-Git @('tag', '-a', $tag, '-m', "$($info.Name) v$new") | Out-Null
}

# ---------------------------------------------------------------- 結果
$head = (Invoke-Git @('log', '-1', '--format=%h %s')) -join ''
Write-Host ""
Write-Host "================ 完成" -ForegroundColor Green
Write-Host "  exe    : dist\$($info.Name)\$($info.Config.name)(v$new).exe"
Write-Host "  HEAD   : $head"
if (-not $NoTag) { Write-Host "  tag    : $tag" }
Write-Host ""
Write-Host "推上 GitHub（確認沒問題再推）:" -ForegroundColor Cyan
Write-Host "  git push origin $branch"
if (-not $NoTag) { Write-Host "  git push origin $tag" }
