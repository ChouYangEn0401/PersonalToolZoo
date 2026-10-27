<#
.SYNOPSIS
    用工具自己的環境，從原始碼執行它（不打包）。每個工具資料夾裡的 run.bat 就是呼叫這支。

.DESCRIPTION
    1. 找出這個工具該用的環境：有第三方套件 → tools\<tool>\.venv；只用標準庫 → 根目錄共用的 .venv
    2. 環境不存在、或裝的版本跟 requirements 不符，就自動建好／同步（跟 build.ps1 用同一套規則）
    3. 用那個環境的 python 執行 tool.json 的 entry，工作目錄是工具資料夾

    不會用到電腦上其他的 Python 或套件，所以不會載入錯的版本。
    --check 只做 1、2，再把 entry 載入一次（不執行 __main__，不會開視窗）確認所有 import 都找得到。

.EXAMPLE
    .\scripts\run.ps1 renamer                                # 開 File Renamer（名稱可以打不完整）
    .\scripts\run.ps1 notes https://youtu.be/xxxx -p news     # 工具名稱後面的參數原封不動交給工具
    .\scripts\run.ps1 notes --check                          # 只準備環境並確認 import 得到
    .\scripts\run.ps1 --check-all                            # 每個工具都 --check 一次
#>
# 刻意不用 param()：工具自己的參數（例如 -p news）要原封不動傳下去，不能被 PowerShell 當成這支腳本的參數

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\_common.ps1"

$argv = @($args)
if ($argv.Count -eq 0) {
    Write-Host "用法: .\scripts\run.ps1 <工具名稱> [--check] [給工具的參數...]   或   .\scripts\run.ps1 --check-all" -ForegroundColor Yellow
    exit 2
}

# 載入 entry 但不執行 __main__：import 失敗就是環境或路徑有問題
$CheckCode = @'
import importlib.util, os, sys
entry = os.path.abspath(sys.argv[1])
sys.path.insert(0, os.path.dirname(entry))
spec = importlib.util.spec_from_file_location("__toolzoo_check__", entry)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
print("    import OK:", os.path.basename(entry), "| python", sys.version.split()[0], "|", sys.executable)
'@

# 準備好環境，回傳要用的 python 與 entry
function Get-ToolLaunch([string] $name) {
    $info = Get-ToolInfo $name
    $entry = Join-Path $info.Dir $info.Config.entry
    if (-not (Test-Path $entry)) { throw "tools\$name\tool.json 的 entry 不存在: $($info.Config.entry)" }
    Write-Host "==> $name  v$($info.Version)   環境: $($info.EnvLabel)" -ForegroundColor Cyan
    $python = Get-ReadyToolPython $info
    [pscustomobject]@{ Info = $info; Python = $python; Entry = $entry }
}

# --check：載入 entry 一次。輸出用 Out-Host 直接印，才不會混進回傳的 exit code
function Test-ToolImport([pscustomobject] $launch) {
    $tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("toolzoo-check-" + [guid]::NewGuid().ToString('N') + '.py')
    [System.IO.File]::WriteAllText($tmp, $CheckCode, $Utf8NoBom)
    $prevUtf8 = $env:PYTHONUTF8
    $env:PYTHONUTF8 = '1'            # 只有檢查時用：路徑或訊息有中文時印得出來
    Push-Location $launch.Info.Dir
    try {
        $prev = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        & $launch.Python $tmp $launch.Entry | Out-Host
        $code = $LASTEXITCODE
        $ErrorActionPreference = $prev
    }
    finally {
        Pop-Location
        $env:PYTHONUTF8 = $prevUtf8
        Remove-Item $tmp -ErrorAction SilentlyContinue
    }
    return $code
}

if ($argv[0] -eq '--check-all') {
    $failed = @()
    foreach ($t in Get-AllTools) {
        try { if ((Test-ToolImport (Get-ToolLaunch $t)) -ne 0) { $failed += $t } }
        catch { Write-Host "    FAILED: $($_.Exception.Message)" -ForegroundColor Red; $failed += $t }
    }
    Write-Host ""
    if ($failed.Count) { Write-Host "有問題: $($failed -join ', ')" -ForegroundColor Red; exit 1 }
    Write-Host "全部 OK" -ForegroundColor Green
    exit 0
}

$names = @(Resolve-ToolTargets @($argv[0]) '執行' $false)
if ($names.Count -eq 0) { exit 2 }
$rest = @($argv | Select-Object -Skip 1)
$launch = Get-ToolLaunch $names[0]
if ($rest.Count -gt 0 -and $rest[0] -eq '--check') {
    exit (Test-ToolImport $launch)
}

# 真正執行：放在腳本最外層、不擷取輸出，工具才拿得到真正的主控台（CLI 的互動詢問、進度列才正常）。
# 不設 PYTHONUTF8，跟打包的 exe 行為一致。
$ErrorActionPreference = 'Continue'
Push-Location $launch.Info.Dir
& $launch.Python $launch.Entry @rest
$code = $LASTEXITCODE
Pop-Location
exit $code
