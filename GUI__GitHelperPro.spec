# -*- mode: python ; coding: utf-8 -*-

import os
import sys

# Ensure project root is on path so we can import src.version
sys.path.insert(0, os.path.abspath('.'))
try:
    from src.version import __version__ as _ver
except Exception:
    _ver = "0.0.0"

# exe base name will include version: e.g. GUI__GitHelperPro(v1.5.0)
exe_name = f"GUI__GitHelperPro(v{_ver})"

# collect data files from folders (language, data, etc.) so they are bundled
datas = []
def _collect_folder(src_dir, dest_dir):
    for root, _, files in os.walk(src_dir):
        for fname in files:
            src = os.path.join(root, fname)
            rel = os.path.relpath(root, src_dir)
            target = os.path.join(dest_dir, rel) if rel != '.' else dest_dir
            datas.append((src, target))

if os.path.isdir('language'):
    _collect_folder('language', 'language')
if os.path.isdir('data'):
    _collect_folder('data', 'data')

a = Analysis(
    ['GUI__GitHelperPro.py'],
    pathex=[os.path.abspath('.')],
    binaries=[],
    datas=datas,
    hiddenimports=[],
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
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
