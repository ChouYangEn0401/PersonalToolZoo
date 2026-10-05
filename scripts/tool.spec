# -*- mode: python ; coding: utf-8 -*-
"""
PersonalToolZoo 共用 build spec
===============================
所有工具共用這一份，不要在各工具資料夾裡再放自己的 .spec。

關鍵：所有路徑都以「工具資料夾」為基準解析，絕不使用 '.'，
      所以不管你在哪個目錄下 build，結果都一樣。
      工具資料夾由環境變數 TOOLZOO_TOOL_DIR 指定（scripts/build.ps1 會設好）。
"""
import json
import os
import sys

TOOL_DIR = os.environ.get("TOOLZOO_TOOL_DIR")
if not TOOL_DIR:
    raise SystemExit("TOOLZOO_TOOL_DIR 未設定 —— 請用 scripts\build.ps1 <tool> 來 build")
TOOL_DIR = os.path.abspath(TOOL_DIR)

with open(os.path.join(TOOL_DIR, "tool.json"), "r", encoding="utf-8-sig") as _f:
    cfg = json.load(_f)


def tool_path(*parts):
    return os.path.join(TOOL_DIR, *parts)


# 讓 entry script 的 import（例如 from src.core...）以工具資料夾為根
sys.path.insert(0, TOOL_DIR)

# ---- 版本號（必填）: 唯一來源是 tool.json 的 version_from 指到的檔案裡的 __version__ ----
# 程式的視窗標題也 import 同一個 __version__，所以改一個地方，檔名跟程式內顯示一起變。
if not cfg.get("version_from"):
    raise SystemExit(f"[tool.spec] {TOOL_DIR}\\tool.json 缺 version_from（版本號規則見根目錄 README）")
_vf = tool_path(cfg["version_from"])
if not os.path.isfile(_vf):
    raise SystemExit(f"[tool.spec] version_from 指到的檔案不存在 -> {_vf}")
_ns = {}
with open(_vf, "r", encoding="utf-8") as _f:
    exec(compile(_f.read(), _vf, "exec"), _ns)
version = _ns.get("__version__")
if not version:
    raise SystemExit(f"[tool.spec] {_vf} 裡沒有 __version__")

exe_name = f"{cfg['name']}(v{version})"

# ---- 要一起打包進 exe 的資料檔 / 資料夾 ----
datas = []
for item in cfg.get("include", []):
    src = tool_path(item)
    if os.path.isdir(src):
        for root, _dirs, files in os.walk(src):
            rel = os.path.relpath(root, TOOL_DIR)
            for fname in files:
                datas.append((os.path.join(root, fname), rel))
    elif os.path.isfile(src):
        datas.append((src, os.path.dirname(item) or "."))
    else:
        print(f"[tool.spec] WARNING: include 指定的路徑不存在 -> {item}")

binaries = []
hiddenimports = list(cfg.get("hiddenimports", []))
for pkg in cfg.get("collect_all", []):
    from PyInstaller.utils.hooks import collect_all
    _d, _b, _h = collect_all(pkg)
    datas += _d
    binaries += _b
    hiddenimports += _h

a = Analysis(
    [tool_path(cfg["entry"])],
    pathex=[TOOL_DIR],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=cfg.get("excludes", []),
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=exe_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=bool(cfg.get("console", False)),
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=(tool_path(cfg["icon"]) if cfg.get("icon") else None),
)
