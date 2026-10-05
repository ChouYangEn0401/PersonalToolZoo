<#
    build.ps1 / setup-venv.ps1 / release.ps1 / bump-version.ps1 共用的 helper，
    用 dot-source 載入：  . "$PSScriptRoot\_common.ps1"

    全 repo 的規則只定義在這裡：
      環境  - 工具的 requirements.txt 有第三方套件 → tools\<name>\.venv（專屬）
              只用標準庫                          → 根目錄 .venv（共用）
      版本  - tool.json 的 version_from 指到的檔案裡的 __version__ = "X.Y.Z" 是唯一來源
      tag   - <tag_prefix>_v<X.Y.Z>
#>

$Root       = Split-Path -Parent $PSScriptRoot
$ToolsDir   = Join-Path $Root 'tools'
$DevReqs    = Join-Path $Root 'requirements-dev.txt'
$CheckDeps  = Join-Path $PSScriptRoot 'check_deps.py'
$RootPython = Join-Path $Root '.venv\Scripts\python.exe'
$Utf8NoBom  = New-Object System.Text.UTF8Encoding $false
$VersionPattern = '(__version__\s*=\s*)([''"])([^''"]*)([''"])'


# ================================================================ 外部程式
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


# ================================================================ 工具資訊
function Get-AllTools {
    if (-not (Test-Path $ToolsDir)) { return @() }
    @(Get-ChildItem -Path $ToolsDir -Directory |
        Where-Object { $_.Name -notlike '_*' } |
        Where-Object { Test-Path (Join-Path $_.FullName 'tool.json') } |
        Select-Object -ExpandProperty Name)
}

function Get-ToolConfig([string] $toolDir) {
    $text = [System.IO.File]::ReadAllText((Join-Path $toolDir 'tool.json'), $Utf8NoBom)
    $text.TrimStart([char]0xFEFF) | ConvertFrom-Json
}

# requirements.txt 裡真正的套件行（去掉註解與空行）
function Get-ToolDeps([string] $toolDir) {
    $req = Join-Path $toolDir 'requirements.txt'
    if (-not (Test-Path $req)) { return @() }
    @([System.IO.File]::ReadAllLines($req, $Utf8NoBom) |
        ForEach-Object { ($_ -split ' #', 2)[0].Trim().TrimStart([char]0xFEFF) } |
        Where-Object { $_ -and -not $_.StartsWith('#') })
}

# 一個工具的所有資訊。版本號不合規則直接報錯（跟 tool.spec 的規則一致）。
function Get-ToolInfo([string] $name) {
    $dir = Join-Path $ToolsDir $name
    if (-not (Test-Path (Join-Path $dir 'tool.json'))) { throw "tools\$name\tool.json 不存在" }
    $cfg = Get-ToolConfig $dir

    if (-not $cfg.version_from) { throw "tools\$name\tool.json 缺 version_from（版本號規則見根目錄 README）" }
    $vf = Join-Path $dir $cfg.version_from
    if (-not (Test-Path $vf)) { throw "tools\$name\tool.json 的 version_from 指到不存在的檔案: $($cfg.version_from)" }
    $m = [regex]::Match([System.IO.File]::ReadAllText($vf, $Utf8NoBom), $VersionPattern)
    if (-not $m.Success) { throw "tools\$name\$($cfg.version_from) 裡找不到 __version__ = `"X.Y.Z`"" }
    $version = $m.Groups[3].Value

    $hasDeps  = (Get-ToolDeps $dir).Count -gt 0
    $ownVenv  = Join-Path $dir '.venv\Scripts\python.exe'
    $python   = if ($hasDeps -or (Test-Path $ownVenv)) { $ownVenv } else { $RootPython }
    $envLabel = if ($python -eq $ownVenv) { "tools\$name\.venv" } else { '.venv (共用)' }
    $tagPrefix = if ($cfg.tag_prefix) { $cfg.tag_prefix } else { $cfg.name }

    # 會被打包進 exe 的原始碼位置（repo 相對路徑）：工具資料夾本身 + tool.json 的 pathex
    # （例如 "../../libs" 共用套件）。release 前要確認這些地方都沒有未 commit 的修改。
    $rootFull = [System.IO.Path]::GetFullPath($Root).TrimEnd('\') + '\'
    $sources = @("tools/$name")
    foreach ($p in @($cfg.pathex | Where-Object { $_ })) {
        $full = [System.IO.Path]::GetFullPath((Join-Path $dir $p))
        if (-not $full.StartsWith($rootFull, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "tools\$name\tool.json 的 pathex 指到 repo 外面: $p"
        }
        $sources += $full.Substring($rootFull.Length).Replace('\', '/')
    }

    [pscustomobject]@{
        Name        = $name
        Dir         = $dir
        Config      = $cfg
        VersionFile = $vf
        Version     = $version
        TagPrefix   = $tagPrefix
        Tag         = "$($tagPrefix)_v$version"
        ExeName     = "$($cfg.name)(v$version).exe"     # 跟 tool.spec 的命名規則一致
        DistDir     = Join-Path $Root "dist\$name"
        WorkDir     = Join-Path $Root "build\$name"
        HasDeps     = $hasDeps
        Python      = $python
        EnvLabel    = $envLabel
        SourcePaths = $sources
    }
}

function Set-ToolVersion([pscustomobject] $info, [string] $newVersion) {
    $text = [System.IO.File]::ReadAllText($info.VersionFile, $Utf8NoBom)
    $re = New-Object System.Text.RegularExpressions.Regex $VersionPattern
    $new = $re.Replace($text, { param($m) $m.Groups[1].Value + $m.Groups[2].Value + $newVersion + $m.Groups[4].Value }, 1)
    [System.IO.File]::WriteAllText($info.VersionFile, $new, $Utf8NoBom)
}

# patch / minor / major / X.Y.Z → 新版本號
function Get-BumpedVersion([string] $current, [string] $bump) {
    if ($bump -match '^v?(\d+\.\d+\.\d+)$') { return $Matches[1] }
    if ($current -notmatch '^(\d+)\.(\d+)\.(\d+)$') { throw "目前版本 '$current' 不是 X.Y.Z 格式，請直接指定新版本號" }
    $maj, $min, $pat = [int]$Matches[1], [int]$Matches[2], [int]$Matches[3]
    switch ($bump.ToLower()) {
        'patch' { return "$maj.$min.$($pat + 1)" }
        'minor' { return "$maj.$($min + 1).0" }
        'major' { return "$($maj + 1).0.0" }
        default { throw "看不懂 '$bump'：請用 patch / minor / major 或 X.Y.Z" }
    }
}


# 互動選擇怎麼改版本號。回傳 patch / minor / major / X.Y.Z / keep；取消回傳 $null。
function Read-BumpChoice([string] $current, [bool] $allowKeep = $false) {
    Write-Host ""
    Write-Host "目前版本 v$current，要怎麼改？" -ForegroundColor Cyan
    $opts = @(
        @('patch', "修 bug、小調整      → v$(Get-BumpedVersion $current 'patch')"),
        @('minor', "加功能              → v$(Get-BumpedVersion $current 'minor')"),
        @('major', "大改版 / 不相容     → v$(Get-BumpedVersion $current 'major')"),
        @('custom', '自己輸入版本號'))
    if ($allowKeep) { $opts += ,@('keep', "不改，用目前的 v$current") }
    for ($i = 0; $i -lt $opts.Count; $i++) { Write-Host ("  [{0}] {1,-7} {2}" -f ($i + 1), $opts[$i][0], $opts[$i][1]) }
    while ($true) {
        $a = Read-Answer "  編號；Enter 取消"
        if (-not $a) { return $null }
        if ($a -match '^v?\d+\.\d+\.\d+$') { return $a.TrimStart('v') }
        $pick = $null
        if ($a -match '^\d+$' -and [int]$a -ge 1 -and [int]$a -le $opts.Count) { $pick = $opts[[int]$a - 1][0] }
        elseif ($opts | Where-Object { $_[0] -eq $a.ToLower() }) { $pick = $a.ToLower() }
        if ($pick -eq 'custom') {
            $v = Read-Answer "  新版本號 (X.Y.Z)"
            if ($v -match '^v?\d+\.\d+\.\d+$') { return $v.TrimStart('v') }
            Write-Host "  格式要是 X.Y.Z" -ForegroundColor Yellow
            continue
        }
        if ($pick) { return $pick }
        Write-Host "  看不懂 '$a'" -ForegroundColor Yellow
    }
}


# ================================================================ 工具名稱（寬鬆比對）
function ConvertTo-LooseKey([string] $s) { ($s.ToLower() -replace '[^a-z0-9]', '') }

# 接受：資料夾名稱、Tab 補完出來的路徑（.\tools\hash-my-file\）、tool.json 的 name、
#       tag_prefix、不分大小寫、忽略 - _ 空白，以及唯一的開頭／片段（例如 hash、excel）。
function Resolve-ToolName([string] $query) {
    $all = Get-AllTools
    $q = $query.Trim().Trim('"', "'").TrimEnd('\', '/')
    if ($q -match '[\\/]') { $q = Split-Path $q -Leaf }

    $cands = foreach ($t in $all) {
        $cfg = Get-ToolConfig (Join-Path $ToolsDir $t)
        [pscustomobject]@{ Name = $t; Keys = @(
            (ConvertTo-LooseKey $t),
            (ConvertTo-LooseKey $cfg.name),
            (ConvertTo-LooseKey ($cfg.name -replace '^GUI_+', '')),
            (ConvertTo-LooseKey $cfg.tag_prefix)) | Where-Object { $_ } }
    }
    $k = ConvertTo-LooseKey $q
    if (-not $k) { throw "工具名稱是空的" }

    foreach ($rule in @(
        { param($c) $c.Keys -contains $k },
        { param($c) @($c.Keys | Where-Object { $_.StartsWith($k) }).Count -gt 0 },
        { param($c) @($c.Keys | Where-Object { $_.Contains($k) }).Count -gt 0 })) {
        $hit = @($cands | Where-Object { & $rule $_ })
        if ($hit.Count -eq 1) { return $hit[0].Name }
        if ($hit.Count -gt 1) {
            throw "'$query' 符合不只一個工具：$(($hit | ForEach-Object Name) -join ', ') —— 打長一點"
        }
    }
    throw "找不到工具 '$query'。可用的工具：$($all -join ', ')"
}


# ================================================================ 互動
function Read-Answer([string] $prompt) {
    try { $a = Read-Host $prompt } catch { return $null }
    if ($null -eq $a) { return $null }
    $a.Trim()
}

function Confirm-YesNo([string] $question, [bool] $default) {
    $hint = if ($default) { '[Y/n]' } else { '[y/N]' }
    $a = Read-Answer "$question $hint"
    if (-not $a) { return $default }
    $a -match '^(y|yes|是|好)$'
}

function Write-ToolTable([string[]] $tools) {
    $i = 0
    foreach ($t in $tools) {
        $i++
        try {
            $info = Get-ToolInfo $t
            $ver = "v$($info.Version)"
            $envState = if (Test-Path $info.Python) { $info.EnvLabel } else { "$($info.EnvLabel) (還沒建，build 時會自動建)" }
        }
        catch { $ver = '??'; $envState = "設定有誤: $($_.Exception.Message)" }
        Write-Host ("  [{0}] {1,-24} {2,-10} {3}" -f $i, $t, $ver, $envState)
    }
}

# 顯示編號選單讓使用者挑工具。可輸入：編號（1 3 / 1,3 / 1-3）、a = 全部、名稱片段；Enter 取消。
function Read-ToolSelection([string] $verb, [bool] $multiple) {
    $all = Get-AllTools
    Write-Host ""
    Write-Host "選擇要「$verb」的工具：" -ForegroundColor Cyan
    Write-ToolTable $all
    Write-Host ""
    $hint = if ($multiple) { '編號（可多選：1 3 或 1-3）、a = 全部、或打名稱；Enter 取消' } else { '編號或名稱；Enter 取消' }
    while ($true) {
        $a = Read-Answer "  $hint"
        if (-not $a -or $a -match '^(q|quit|exit)$') { return @() }
        if ($multiple -and $a -match '^(a|all|全部)$') { return $all }
        try {
            $picked = @()
            foreach ($tok in ($a -split '[\s,]+' | Where-Object { $_ })) {
                if ($tok -match '^(\d+)-(\d+)$') {
                    foreach ($n in [int]$Matches[1]..[int]$Matches[2]) {
                        if ($n -lt 1 -or $n -gt $all.Count) { throw "沒有編號 $n" }
                        $picked += $all[$n - 1]
                    }
                }
                elseif ($tok -match '^\d+$') {
                    $n = [int]$tok
                    if ($n -lt 1 -or $n -gt $all.Count) { throw "沒有編號 $n" }
                    $picked += $all[$n - 1]
                }
                else { $picked += Resolve-ToolName $tok }
            }
            $picked = @($picked | Select-Object -Unique)
            if (-not $multiple -and $picked.Count -gt 1) { throw "這裡一次只能選一個" }
            return $picked
        }
        catch { Write-Host "  $($_.Exception.Message)" -ForegroundColor Yellow }
    }
}

# 把命令列給的名稱（可能不完整）轉成正式名稱；沒給就跳選單。
function Resolve-ToolTargets([string[]] $queries, [string] $verb, [bool] $multiple) {
    $queries = @($queries | Where-Object { $_ })
    if ($queries.Count -eq 0) { return @(Read-ToolSelection $verb $multiple) }
    @($queries | ForEach-Object { Resolve-ToolName $_ } | Select-Object -Unique)
}

# ================================================================ 環境
function Test-ToolDeps([pscustomobject] $info, [string] $python, [bool] $quiet) {
    $files = @($DevReqs)
    $req = Join-Path $info.Dir 'requirements.txt'
    if (Test-Path $req) { $files += $req }
    $argv = @($CheckDeps)
    if ($quiet) { $argv += '--quiet' }
    Invoke-Native $python ($argv + $files) "依賴檢查 ($($info.Name))"
}

function New-Venv([string] $venvDir, [string] $pythonVersion) {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) { Invoke-Native $py.Source @("-$pythonVersion", '-m', 'venv', $venvDir) "建立 venv" }
    else     { Invoke-Native 'python'   @('-m', 'venv', $venvDir) "建立 venv" }
}

# 建立／更新工具的 venv 並安裝 requirements。$recreate = 先整個砍掉。
function Initialize-ToolEnv([pscustomobject] $info, [bool] $recreate, [string] $pythonVersion = '3.11') {
    $venvDir = Split-Path -Parent (Split-Path -Parent $info.Python)
    $shared  = ($info.Python -eq $RootPython)
    $reqs = @($DevReqs)
    if ($info.HasDeps) { $reqs += (Join-Path $info.Dir 'requirements.txt') }

    if ($recreate -and $shared) {
        Write-Host "    （共用的根目錄 .venv 其他工具也在用，不砍掉，只同步套件）" -ForegroundColor DarkGray
    }
    elseif ($recreate -and (Test-Path $venvDir)) {
        Write-Host "    砍掉舊的 $($info.EnvLabel)" -ForegroundColor Yellow
        Remove-Item $venvDir -Recurse -Force
    }
    if (-not (Test-Path $info.Python)) {
        Write-Host "    建立 $($info.EnvLabel) (Python $pythonVersion)" -ForegroundColor DarkGray
        New-Venv $venvDir $pythonVersion
    }

    $pipArgs = @('-m', 'pip', 'install', '--disable-pip-version-check', '-q')
    foreach ($r in $reqs) { $pipArgs += @('-r', $r) }
    Write-Host "    pip install $(($reqs | ForEach-Object { Split-Path $_ -Leaf }) -join ' + ')  → $($info.EnvLabel)" -ForegroundColor DarkGray
    # requirements 檔是 UTF-8（含中文註解）。pip 預設用系統編碼讀檔，
    # 繁中 Windows 是 cp950 → UnicodeDecodeError。pip 這一步強制 UTF-8 模式。
    $prevUtf8 = $env:PYTHONUTF8
    $env:PYTHONUTF8 = '1'
    try { Invoke-Native $info.Python $pipArgs "pip install ($($info.EnvLabel))" }
    finally { $env:PYTHONUTF8 = $prevUtf8 }
}

# build 前呼叫：確保環境存在且符合 requirements，不符合就自動修，修不好才報錯。
# 回傳可以用的 python.exe。
function Get-ReadyToolPython([pscustomobject] $info) {
    if (-not (Test-Path $info.Python)) {
        Write-Host "    環境還沒建，自動建立..." -ForegroundColor Yellow
        Initialize-ToolEnv $info $false
    }
    try { Test-ToolDeps $info $info.Python $true; return $info.Python }
    catch { Write-Host "    環境跟 requirements 不一致，自動同步..." -ForegroundColor Yellow }

    Initialize-ToolEnv $info $false
    try { Test-ToolDeps $info $info.Python $true; return $info.Python }
    catch { Write-Host "    同步後還是不一致，整個重建..." -ForegroundColor Yellow }

    Initialize-ToolEnv $info $true
    Test-ToolDeps $info $info.Python $false
    $info.Python
}
