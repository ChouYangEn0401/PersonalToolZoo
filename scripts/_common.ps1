<#
    build.ps1 / setup-venv.ps1 共用的 helper，用 dot-source 載入：  . "$PSScriptRoot\_common.ps1"

    環境規則（全 repo 唯一一份定義）：
      - 工具的 requirements.txt 有第三方套件 → 必須用自己的 tools\<name>\.venv
      - 只用標準庫的工具                      → 用根目錄共用的 .venv
#>

$Root       = Split-Path -Parent $PSScriptRoot
$ToolsDir   = Join-Path $Root 'tools'
$DevReqs    = Join-Path $Root 'requirements-dev.txt'
$CheckDeps  = Join-Path $PSScriptRoot 'check_deps.py'
$RootPython = Join-Path $Root '.venv\Scripts\python.exe'


function Get-AllTools {
    if (-not (Test-Path $ToolsDir)) { return @() }
    @(Get-ChildItem -Path $ToolsDir -Directory |
        Where-Object { $_.Name -notlike '_*' } |
        Where-Object { Test-Path (Join-Path $_.FullName 'tool.json') } |
        Select-Object -ExpandProperty Name)
}

function Get-ToolDir([string] $name) {
    $dir = Join-Path $ToolsDir $name
    if (-not (Test-Path (Join-Path $dir 'tool.json'))) {
        throw "tools\$name\tool.json 不存在 —— 用 .\scripts\build.ps1 -List 看有哪些工具"
    }
    $dir
}

function Get-ToolRequirementsFile([string] $toolDir) {
    Join-Path $toolDir 'requirements.txt'
}

# requirements.txt 裡真正的套件行（去掉註解與空行）
function Get-ToolDeps([string] $toolDir) {
    $req = Get-ToolRequirementsFile $toolDir
    if (-not (Test-Path $req)) { return @() }
    @(Get-Content $req -Encoding UTF8 |
        ForEach-Object { ($_ -split ' #', 2)[0].Trim() } |
        Where-Object { $_ -and -not $_.StartsWith('#') })
}

function Get-ToolVenvPython([string] $toolDir) {
    Join-Path $toolDir '.venv\Scripts\python.exe'
}

# 依上面的環境規則決定這個工具該用哪個 python；不合規則就直接報錯，不默默退回。
function Resolve-ToolPython([string] $name) {
    $toolDir = Get-ToolDir $name
    $own     = Get-ToolVenvPython $toolDir

    if (Test-Path $own) { return $own }

    if ((Get-ToolDeps $toolDir).Count -gt 0) {
        throw "tools\$name 有第三方依賴，但還沒有自己的 .venv。先跑:  .\scripts\setup-venv.ps1 $name"
    }
    if (-not (Test-Path $RootPython)) {
        throw "根目錄共用的 .venv 還沒建。先跑:  .\scripts\setup-venv.ps1 $name"
    }
    $RootPython
}

# 跑外部程式（python / pip / pyinstaller）。
# Windows PowerShell 5.1 在 $ErrorActionPreference='Stop' 下，外部程式往 stderr 寫字
# （PyInstaller 的 INFO log、pip 的 notice）有時會被當成錯誤中斷，所以這裡暫時放寬，
# 改用 exit code 判斷成敗。輸出一律直接印到畫面（Out-Host），
# 不然會混進呼叫端函式的回傳值裡。
function Invoke-Native([string] $exe, [string[]] $arguments, [string] $what) {
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { & $exe @arguments | Out-Host }
    finally { $ErrorActionPreference = $prev }
    if ($LASTEXITCODE -ne 0) { throw "$what 失敗 (exit code $LASTEXITCODE)" }
}

function Test-ToolDeps([string] $name, [string] $python) {
    $toolDir = Get-ToolDir $name
    $files = @($DevReqs)
    $req = Get-ToolRequirementsFile $toolDir
    if (Test-Path $req) { $files += $req }
    Invoke-Native $python (@($CheckDeps) + $files) "依賴檢查 ($name)"
}
