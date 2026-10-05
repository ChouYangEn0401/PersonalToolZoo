"""使用者資料夾：設定、金鑰、歷史紀錄放這裡，不放在工具資料夾或 exe 旁邊。

onefile exe 會把自己解到一個關掉就刪的暫存資料夾，寫在 ``__file__`` 旁邊的東西
下次開就不見了；工具資料夾又在 repo 裡，不該混進個人資料。所以一律寫到：

    Windows : %APPDATA%\\PersonalToolZoo\\<tool>\\
    其他    : ~/.local/share/PersonalToolZoo/<tool>/

想搬到別的地方，設環境變數 TOOLZOO_DATA_DIR 即可。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "PersonalToolZoo"


def data_root() -> Path:
    """全部工具共用的根資料夾（金鑰檔就在這一層）。"""
    override = os.environ.get("TOOLZOO_DATA_DIR")
    if override:
        root = Path(override)
    elif sys.platform == "win32":
        root = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / APP_NAME
    else:
        root = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / APP_NAME
    root.mkdir(parents=True, exist_ok=True)
    return root


def tool_data_dir(tool: str) -> Path:
    """某個工具自己的資料夾，例如 tool_data_dir("video-notes")。"""
    path = data_root() / tool
    path.mkdir(parents=True, exist_ok=True)
    return path


def downloads_dir() -> Path:
    """使用者的「下載」資料夾（找不到就退回家目錄底下的 Downloads）。"""
    if sys.platform == "win32":
        try:
            import ctypes

            # FOLDERID_Downloads；使用者把「下載」搬到 D 槽時，這樣才拿得到真正的位置
            guid = ctypes.c_char_p(
                b"\x90\xe2\x4d\x37\x3f\x12\x65\x45\x91\x64\x39\xc4\x92\x5e\x46\x7b"
            )
            buf = ctypes.c_wchar_p()
            if ctypes.windll.shell32.SHGetKnownFolderPath(guid, 0, None, ctypes.byref(buf)) == 0:
                path = Path(buf.value)
                ctypes.windll.ole32.CoTaskMemFree(buf)
                return path
        except Exception:  # noqa: BLE001 — 拿不到就用預設位置
            pass
    return Path.home() / "Downloads"
