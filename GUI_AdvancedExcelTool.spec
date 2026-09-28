# -*- mode: python ; coding: utf-8 -*-

import os
import sys

# Ensure project root is on path so local packages (excel_tool) import cleanly
sys.path.insert(0, os.path.abspath('.'))

exe_name = "GUI_AdvancedExcelTool"

# Pull in tkinterdnd2's bundled tkdnd binaries/data (drag & drop support).
# collect_all returns (datas, binaries, hiddenimports) tuples.
datas = []
binaries = []
hiddenimports = []
try:
    from PyInstaller.utils.hooks import collect_all
    _d, _b, _h = collect_all('tkinterdnd2')
    datas += _d
    binaries += _b
    hiddenimports += _h
except Exception:
    pass

a = Analysis(
    ['GUI_AdvancedExcelTool.py'],
    pathex=[os.path.abspath('.')],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
