"""工具的資料與參數放哪裡：一律放在工具自己旁邊，不寫到使用者資料夾（%APPDATA%、家目錄）。

資料（設定、紀錄、快取）：

    從原始碼執行  tools/<tool>/data/          （.gitignore 擋掉 tools/*/data/，不進版控）
    打包的 exe    exe 所在資料夾的 data/      （例如 dist/<tool>/data/）

金鑰與參數放 .env（範本是 repo 根目錄的 .env.example）：

    從原始碼執行  repo 根目錄的 .env
    打包的 exe    exe 旁邊的 .env；exe 放在 repo 的 dist/ 裡時，也讀 repo 根目錄的 .env

環境變數永遠優先於 .env。測試與冒煙測試可以設 TOOLZOO_DATA_DIR 把兩者整個搬走：
資料放 <TOOLZOO_DATA_DIR>/<tool>/，.env 用 <TOOLZOO_DATA_DIR>/.env。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_MARKER = Path("scripts") / "tool.spec"   # 有這個檔案的資料夾就是 repo 根目錄

# load_env() 從哪個 .env 載入了哪些變數（給畫面顯示「金鑰從哪裡讀到的」）
loaded_from: dict[str, Path] = {}


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def exe_dir() -> Path:
    """打包後 exe 所在的資料夾。"""
    return Path(sys.executable).resolve().parent


def _source_repo() -> Path:
    return Path(__file__).resolve().parents[2]   # libs/toolzoo/appdirs.py → repo 根目錄


def _override() -> Path | None:
    value = os.environ.get("TOOLZOO_DATA_DIR", "").strip()
    return Path(value) if value else None


def repo_root() -> Path | None:
    """PersonalToolZoo repo 的根目錄；打包的 exe 不在 repo 裡時回傳 None。"""
    start = exe_dir() if is_frozen() else _source_repo()
    for folder in (start, *start.parents):
        if (folder / REPO_MARKER).is_file():
            return folder
    return None


def tool_data_dir(tool: str) -> Path:
    """某個工具存設定、紀錄、快取的資料夾，例如 tool_data_dir("video-notes")。"""
    override = _override()
    if override:
        path = override / tool
    elif is_frozen():
        path = exe_dir() / "data"
    else:
        path = _source_repo() / "tools" / tool / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def env_files() -> list[Path]:
    """要讀的 .env，前面的優先。"""
    override = _override()
    if override:
        return [override / ".env"]
    files: list[Path] = []
    if is_frozen():
        files.append(exe_dir() / ".env")
    repo = repo_root()
    if repo:
        files.append(repo / ".env")
    return list(dict.fromkeys(files))


def env_file() -> Path:
    """要寫入（例如存金鑰）時用的 .env：在 repo 裡就寫 repo 根目錄的，否則寫 exe 旁邊的。"""
    override = _override()
    if override:
        override.mkdir(parents=True, exist_ok=True)
        return override / ".env"
    repo = repo_root()
    if repo:
        return repo / ".env"
    return exe_dir() / ".env"


def read_env_file(path: Path) -> dict[str, str]:
    """讀 KEY=VALUE 格式的 .env。不認得的行直接略過，不會丟例外。"""
    data: dict[str, str] = {}
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return data
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        name, value = line.split("=", 1)
        data[name.strip()] = value.strip().strip('"').strip("'")
    return data


def load_env() -> dict[str, Path]:
    """把 .env 裡的參數載入 os.environ（已經設定的環境變數不覆蓋），回傳載入了哪些。

    範本裡的佔位值（以 ... 結尾，例如 sk-proj-......）不會被載入。
    """
    for path in env_files():
        for name, value in read_env_file(path).items():
            if not value or value.endswith("...") or name in os.environ:
                continue
            os.environ[name] = value
            loaded_from[name] = path
    return dict(loaded_from)


def downloads_dir() -> Path:
    """使用者的「下載」資料夾（找不到就退回家目錄底下的 Downloads）。影片類工具的輸出放這裡。"""
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
