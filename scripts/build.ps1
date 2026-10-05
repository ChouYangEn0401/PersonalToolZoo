<#
.SYNOPSIS
    PersonalToolZoo 統一 builder。

.DESCRIPTION
    所有工具共用 scripts\tool.spec，各工具的差異只寫在 tools\<name>\tool.json。
    所有路徑都以「工具資料夾」為基準解析，所以你站在哪個目錄下執行結果都一樣。

    每次 build 前會先檢查該工具 venv 裡裝的套件符合 requirements，
    不符合就不 build（避免產出一個能 build、但一打開就崩潰的 exe）。

.EXAMPLE
    .\scripts\build.ps1 git-helper-pro          # build 單一工具
    .\scripts\build.ps1 git-helper-pro -Smoke   # build 完實際啟動 exe 檢查會不會崩潰
    .\scripts\build.ps1 -All -Smoke             # 全部 build + 冒煙測試（發 release 前用這個）
    .\scripts\build.ps1 -List                   # 列出有哪些工具、用哪個環境、版本
    .\scripts\build.ps1 hash-my-file -Clean -Smoke   # 清掉這個工具的快取後從頭 build（發 release 用）
    .\scripts\build.ps1 -Clean                  # 清掉整個 build\ 與 dist\
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string] $Tool,

    [switch] $All,
    [switch] $List,
    [switch] $Clean,

    # build 完把 exe 開起來 N 秒，出現 PyInstaller 的錯誤視窗或程式提早崩潰就算失敗
    [switch] $Smoke,
    [int]    $SmokeSeconds = 10
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\_common.ps1"

$Spec = Join-Path $PSScriptRoot 'tool.spec'


function Get-ToolVersion([string] $toolDir) {
    $cfg = Get-Content (Join-Path $toolDir 'tool.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($cfg.version_from) {
        $vf = Join-Path $toolDir $cfg.version_from
        if (Test-Path $vf) {
            $m = Select-String -Path $vf -Pattern '__version__\s*=\s*[''"]([^''"]+)[''"]' | Select-Object -First 1
            if ($m) { return $m.Matches[0].Groups[1].Value }
        }
    }
    if ($cfg.version) { return $cfg.version }
    ''
}

function Get-ExeBaseName([string] $toolDir) {
    $cfg = Get-Content (Join-Path $toolDir 'tool.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $v = Get-ToolVersion $toolDir
    if ($v) { "$($cfg.name)(v$v)" } else { $cfg.name }
}

function Format-Version([string] $v) { if ($v) { "v$v" } else { '(無版本號)' } }

function Get-ProcessTree([int] $id) {
    $ids = @($id)
    foreach ($c in @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$id")) {
        $ids += Get-ProcessTree ([int] $c.ProcessId)
    }
    $ids
}

# 啟動 exe，盯著它 $SmokeSeconds 秒：
#   - 出現 "Unhandled exception in script" 視窗（windowed exe 崩潰）→ 失敗
#   - 提早結束且 exit code 非 0（console exe 崩潰）              → 失敗
#   - 撐到時間到                                                 → 通過，關掉它
function Test-ExeSmoke([System.IO.FileInfo] $exe) {
    Write-Host "    smoke: 啟動 $($exe.Name) 觀察 $SmokeSeconds 秒..." -ForegroundColor DarkGray
    # 複製到暫存資料夾再跑：有些工具會在 exe 旁邊寫 log / 設定檔，不要弄髒 dist 資料夾
    $sandbox = Join-Path $env:TEMP ("toolzoo-smoke-" + [guid]::NewGuid().ToString('N').Substring(0, 8))
    New-Item -ItemType Directory -Path $sandbox | Out-Null
    $copy = Join-Path $sandbox $exe.Name
    Copy-Item $exe.FullName $copy
    $p = Start-Process -FilePath $copy -WorkingDirectory $sandbox -PassThru
    $verdict = $null
    $deadline = (Get-Date).AddSeconds($SmokeSeconds)
    try {
        while ((Get-Date) -lt $deadline) {
            Start-Sleep -Milliseconds 500
            foreach ($id in (Get-ProcessTree $p.Id)) {
                $pr = Get-Process -Id $id -ErrorAction SilentlyContinue
                if ($pr -and $pr.MainWindowTitle -like 'Unhandled exception*') {
                    $verdict = "跳出 PyInstaller 錯誤視窗（$($pr.MainWindowTitle)）—— 直接執行 exe 看 traceback"
                }
            }
            if ($verdict) { break }
            if ($p.HasExited) {
                if ($p.ExitCode -ne 0) { $verdict = "程式提早結束，exit code $($p.ExitCode)" }
                break
            }
        }
    }
    finally {
        if (-not $p.HasExited) {
            $tree = @(Get-ProcessTree $p.Id)
            [array]::Reverse($tree)
            foreach ($id in $tree) { Stop-Process -Id $id -Force -ErrorAction SilentlyContinue }
            Start-Sleep -Milliseconds 500   # 等檔案鎖放掉
        }
        Remove-Item $sandbox -Recurse -Force -ErrorAction SilentlyContinue
    }
    if ($verdict) { throw "smoke test 失敗: $verdict" }
    Write-Host "    smoke: OK" -ForegroundColor Green
}

function Build-Tool([string] $name) {
    $toolDir  = Get-ToolDir $name
    $distPath = Join-Path $Root "dist\$name"
    $workPath = Join-Path $Root "build\$name"

    Write-Host ""
    Write-Host "==> building $name $(Format-Version (Get-ToolVersion $toolDir))" -ForegroundColor Cyan

    $python = Resolve-ToolPython $name
    Write-Host "    python: $python" -ForegroundColor DarkGray

    try { Test-ToolDeps $name $python }
    catch { throw "$($_.Exception.Message) —— 環境跟 requirements 不一致，先跑:  .\scripts\setup-venv.ps1 $name -Force" }

    $env:TOOLZOO_TOOL_DIR = $toolDir
    try {
        Invoke-Native $python @('-m', 'PyInstaller', $Spec, '--noconfirm', '--distpath', $distPath, '--workpath', $workPath) "build $name"
    }
    finally {
        Remove-Item Env:\TOOLZOO_TOOL_DIR -ErrorAction SilentlyContinue
    }

    # 產物檔名規則跟 tool.spec 一致：<name>(v<version>).exe
    # （不能用時間戳找：輸入沒變時 PyInstaller 會判定 EXE 已是最新而不重寫檔案）
    $exePath = Join-Path $distPath "$(Get-ExeBaseName $toolDir).exe"
    if (-not (Test-Path $exePath)) { throw "build $name 結束了，但找不到預期的產物 $exePath" }
    $exe = Get-Item $exePath

    $mb = [math]::Round($exe.Length / 1MB, 1)
    Write-Host "    OK -> dist\$name\$($exe.Name)  ($mb MB)" -ForegroundColor Green

    $old = @(Get-ChildItem -Path $distPath -Filter *.exe | Where-Object { $_.FullName -ne $exe.FullName })
    foreach ($o in $old) { Write-Host "    (dist\$name\ 裡還有舊的 $($o.Name)，要的話自己刪)" -ForegroundColor DarkYellow }

    if ($Smoke) { Test-ExeSmoke $exe }
}


# ---------------------------------------------------------------- main
if ($Clean) {
    # 有指定工具 → 只清那個工具的 build\<tool>、dist\<tool>；沒指定 → 整個 build\、dist\
    $cleanDirs = if ($Tool -and -not $All) { @("build\$Tool", "dist\$Tool") } else { @('build', 'dist') }
    foreach ($d in $cleanDirs) {
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
    foreach ($t in Get-AllTools) {
        $dir = Join-Path $ToolsDir $t
        $env_ = if (Test-Path (Get-ToolVenvPython $dir)) { "tools\$t\.venv" }
                elseif ((Get-ToolDeps $dir).Count -gt 0) { '(缺 venv → setup-venv.ps1)' }
                else { '.venv (共用)' }
        Write-Host ("  - {0,-24} {1,-12} {2}" -f $t, (Format-Version (Get-ToolVersion $dir)), $env_)
    }
    return
}

$targets = @()
if ($All)        { $targets = Get-AllTools }
elseif ($Tool)   { $targets = @($Tool) }
else {
    Write-Host "用法: .\scripts\build.ps1 <tool> [-Smoke] | -All [-Smoke] | -List | -Clean" -ForegroundColor Yellow
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
        Write-Verbose $_.ScriptStackTrace
    }
}

Write-Host ""
if ($failed.Count -gt 0) {
    Write-Host "完成，但有 $($failed.Count) 個失敗: $($failed -join ', ')" -ForegroundColor Red
    exit 1
}
Write-Host "全部完成 ($($targets.Count) 個工具)" -ForegroundColor Green
