<#
.SYNOPSIS
    PersonalToolZoo 統一 builder。

.DESCRIPTION
    什麼參數都不給 → 跳出選單讓你挑要 build 哪些工具（雙擊根目錄的 build.bat 也是這個）。
    工具名稱可以打不完整：hash、excel、table、HashMyFile、.\tools\hash-my-file\ 都認得；
    打 .\scripts\build.ps1 再按 Tab 可以補完名稱。

    每個工具 build 時會自動：
      1. 準備環境 —— venv 不存在就建、版本跟 requirements 不符就同步（不用先手動 setup）
      2. 用共用的 scripts\tool.spec 打包 → dist\<tool>\<name>(v<版本>).exe
         版本號自動讀 tool.json 的 version_from，不用手打
      3. 冒煙測試 —— 把 exe 開起來 10 秒，崩潰（錯誤視窗 / 提早結束）就判定失敗

.EXAMPLE
    .\scripts\build.ps1                         # 選單
    .\scripts\build.ps1 hash                    # build hash-my-file
    .\scripts\build.ps1 hash table excel        # 一次 build 多個
    .\scripts\build.ps1 -All                    # 全部
    .\scripts\build.ps1 excel -Clean            # 清掉這個工具的快取後從頭 build
    .\scripts\build.ps1 hash -NoSmoke           # 不開 exe 檢查（快一點）
    .\scripts\build.ps1 -List                   # 列出工具、版本、環境
    .\scripts\build.ps1 -Clean                  # 只清掉整個 build\ 與 dist\
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
    [switch] $List,
    [switch] $Clean,
    [switch] $NoSmoke,
    [int]    $SmokeSeconds = 10,

    # 舊參數，冒煙測試現在預設就會做；留著讓舊指令不會出錯
    [switch] $Smoke
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\_common.ps1"

$Spec = Join-Path $PSScriptRoot 'tool.spec'


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

function Build-Tool([string] $name, [bool] $clean, [bool] $smoke) {
    Write-Host ""
    $info = Get-ToolInfo $name
    Write-Host "==> $name  v$($info.Version)" -ForegroundColor Cyan

    if ($clean) {
        foreach ($d in @($info.WorkDir, $info.DistDir)) {
            if (Test-Path $d) { Remove-Item $d -Recurse -Force; Write-Host "    清掉 $($d.Substring($Root.Length + 1))\" -ForegroundColor DarkGray }
        }
    }

    $python = Get-ReadyToolPython $info
    Write-Host "    環境: $($info.EnvLabel)" -ForegroundColor DarkGray

    $env:TOOLZOO_TOOL_DIR = $info.Dir
    try {
        Invoke-Native $python @('-m', 'PyInstaller', $Spec, '--noconfirm', '--log-level', 'WARN',
                                '--distpath', $info.DistDir, '--workpath', $info.WorkDir) "PyInstaller ($name)"
    }
    finally {
        Remove-Item Env:\TOOLZOO_TOOL_DIR -ErrorAction SilentlyContinue
    }

    # 檔名規則跟 tool.spec 一致，直接用算的找產物
    # （不能用時間戳找：輸入沒變時 PyInstaller 會判定 EXE 已是最新而不重寫檔案）
    $exePath = Join-Path $info.DistDir $info.ExeName
    if (-not (Test-Path $exePath)) { throw "build 結束了，但找不到預期的產物 $exePath" }
    $exe = Get-Item $exePath
    Write-Host ("    產物: dist\{0}\{1}  ({2} MB)" -f $name, $exe.Name, [math]::Round($exe.Length / 1MB, 1)) -ForegroundColor Green

    foreach ($o in @(Get-ChildItem $info.DistDir -Filter *.exe | Where-Object { $_.Name -ne $exe.Name })) {
        Write-Host "    (dist\$name\ 裡還有舊版的 $($o.Name)，不需要就刪掉，或下次加 -Clean)" -ForegroundColor DarkYellow
    }

    if ($smoke) { Test-ExeSmoke $exe }
    $exe.FullName
}


# ---------------------------------------------------------------- main
if ($List) {
    Write-Host "tools/:" -ForegroundColor Cyan
    Write-ToolTable (Get-AllTools)
    return
}

if ($Clean -and -not $All -and -not $Tool) {
    foreach ($d in @('build', 'dist')) {
        $p = Join-Path $Root $d
        if (Test-Path $p) { Remove-Item $p -Recurse -Force; Write-Host "removed $d\" -ForegroundColor Yellow }
    }
    return
}

$interactive = -not $All -and -not $Tool
$doClean = [bool] $Clean
$doSmoke = -not $NoSmoke

if ($All) { $targets = Get-AllTools }
else {
    $targets = Resolve-ToolTargets $Tool 'build' $true
    if ($targets.Count -eq 0) {
        Write-Host "沒有選任何工具，結束。" -ForegroundColor Yellow
        Write-Host "用法: .\scripts\build.ps1 [工具名稱...] [-All] [-Clean] [-NoSmoke] [-List]   （詳見 Get-Help .\scripts\build.ps1）"
        return
    }
}

if ($interactive) {
    Write-Host ""
    Write-Host "要 build: $($targets -join ', ')" -ForegroundColor Cyan
    $doClean = Confirm-YesNo "  清掉快取從頭 build？（發 release 前建議）" $false
    $doSmoke = Confirm-YesNo "  build 完把 exe 開起來檢查會不會崩潰？" $true
}

$results = @()
foreach ($t in $targets) {
    try {
        $exe = Build-Tool $t $doClean $doSmoke
        $results += [pscustomobject]@{ Tool = $t; Result = 'OK'; Output = $exe.Substring($Root.Length + 1) }
    }
    catch {
        $results += [pscustomobject]@{ Tool = $t; Result = 'FAILED'; Output = $_.Exception.Message }
        Write-Host "    FAILED: $($_.Exception.Message)" -ForegroundColor Red
        Write-Verbose $_.ScriptStackTrace
    }
}

Write-Host ""
Write-Host "================ 結果" -ForegroundColor Cyan
foreach ($r in $results) {
    $color = if ($r.Result -eq 'OK') { 'Green' } else { 'Red' }
    Write-Host ("  {0,-7} {1,-24} {2}" -f $r.Result, $r.Tool, $r.Output) -ForegroundColor $color
}
$failed = @($results | Where-Object { $_.Result -ne 'OK' })

if ($interactive -and $failed.Count -lt $results.Count) {
    if (Confirm-YesNo "打開 dist 資料夾？" $false) { Invoke-Item (Join-Path $Root 'dist') }
}
if ($failed.Count -gt 0) { exit 1 }
