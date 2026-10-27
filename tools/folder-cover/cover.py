"""把資料夾在檔案總管裡的圖示換成一張圖片（Windows）。畫面在 main.py。

做法跟檔案總管「內容 → 自訂 → 變更圖示」一樣：
1. 把圖片裁成正方形（或補透明邊），存成多尺寸的 folder-cover.ico 放進資料夾（隱藏）。
2. 呼叫 Windows 的 SHGetSetFolderCustomSettings：它會寫 desktop.ini（IconResource）、
   把資料夾設成「唯讀」讓檔案總管去讀 desktop.ini，並通知檔案總管重新整理。
   圖示路徑寫相對路徑，資料夾搬家或換磁碟機也不會失效。

舊版（Change Folder Cover）失敗的原因：沒有先裁成正方形就存 ICO、desktop.ini 用正斜線的絕對路徑、
沒有通知檔案總管更新快取，看起來就像沒有作用。
"""

from __future__ import annotations

import ctypes
import os
import sys
from ctypes import wintypes
from pathlib import Path

from PIL import Image, ImageOps

ICON_NAME = "folder-cover.ico"
ICON_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff")
PREFERRED_NAMES = ("cover", "folder", "poster", "front")   # 自動挑圖時優先用這些檔名

MODE_CROP = "crop"   # 裁掉多的部分，取中間的正方形
MODE_FIT = "fit"     # 整張保留，旁邊補透明

SECTION = ".ShellClassInfo"
FILE_ATTRIBUTE_READONLY = 0x01
FILE_ATTRIBUTE_HIDDEN = 0x02
FILE_ATTRIBUTE_SYSTEM = 0x04
INVALID_FILE_ATTRIBUTES = 0xFFFFFFFF


class CoverError(OSError):
    pass


# ---------------------------------------------------------------- 圖片 → ico
def square(img: Image.Image, mode: str = MODE_CROP) -> Image.Image:
    img = img.convert("RGBA")
    w, h = img.size
    if w == h:
        return img
    if mode == MODE_CROP:
        side = min(w, h)
        left, top = (w - side) // 2, (h - side) // 2
        return img.crop((left, top, left + side, top + side))
    side = max(w, h)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(img, ((side - w) // 2, (side - h) // 2))
    return canvas


def load_square(image_path: str | Path, mode: str = MODE_CROP) -> Image.Image:
    """讀圖（照片會依 EXIF 轉正）並變成正方形。"""
    with Image.open(image_path) as img:
        img = ImageOps.exif_transpose(img)
        img.load()
        return square(img, mode)


def make_icon(image_path: str | Path, icon_path: str | Path, mode: str = MODE_CROP) -> Path:
    """存成內含 16～256 多種尺寸的 .ico（小圖會先放大到 256，檔案總管各種檢視都清楚）。"""
    sq = load_square(image_path, mode)
    if sq.width != 256:
        sq = sq.resize((256, 256), Image.LANCZOS)
    icon_path = Path(icon_path)
    _set_attributes(icon_path, 0)          # 舊的 ico 是隱藏＋系統檔，先解除才寫得進去
    sq.save(icon_path, format="ICO", sizes=ICON_SIZES)
    return icon_path


def find_images(folder: str | Path) -> list[Path]:
    """資料夾第一層的圖片，偏好的檔名（cover、folder…）排前面，其餘照檔名排序。"""
    folder = Path(folder)
    try:
        files = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTS]
    except OSError:
        return []
    return sorted(files, key=lambda p: (p.stem.lower() not in PREFERRED_NAMES, p.name.lower()))


# ---------------------------------------------------------------- Windows API
class SHFOLDERCUSTOMSETTINGS(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("dwMask", wintypes.DWORD),
        ("pvid", ctypes.c_void_p),
        ("pszWebViewTemplate", wintypes.LPWSTR),
        ("cchWebViewTemplate", wintypes.DWORD),
        ("pszWebViewTemplateVersion", wintypes.LPWSTR),
        ("pszInfoTip", wintypes.LPWSTR),
        ("cchInfoTip", wintypes.DWORD),
        ("pclsid", ctypes.c_void_p),
        ("dwFlags", wintypes.DWORD),
        ("pszIconFile", wintypes.LPWSTR),
        ("cchIconFile", wintypes.DWORD),
        ("iIconIndex", ctypes.c_int),
        ("pszLogo", wintypes.LPWSTR),
        ("cchLogo", wintypes.DWORD),
    ]


FCSM_ICONFILE = 0x10
FCS_FORCEWRITE = 0x02
SHCNE_UPDATEDIR = 0x00001000
SHCNE_UPDATEITEM = 0x00002000
SHCNF_PATHW = 0x0005


def _require_windows() -> None:
    if sys.platform != "win32":
        raise CoverError("只支援 Windows")


def _get_attributes(path: Path) -> int:
    attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
    return 0 if attrs == INVALID_FILE_ATTRIBUTES else attrs


def _set_attributes(path: Path, attrs: int) -> None:
    if sys.platform == "win32" and Path(path).exists():
        ctypes.windll.kernel32.SetFileAttributesW(str(path), attrs or 0x80)   # 0x80 = NORMAL


def _notify(folder: Path) -> None:
    shell32 = ctypes.windll.shell32
    shell32.SHChangeNotify(SHCNE_UPDATEITEM, SHCNF_PATHW, ctypes.c_wchar_p(str(folder)), None)
    shell32.SHChangeNotify(SHCNE_UPDATEDIR, SHCNF_PATHW, ctypes.c_wchar_p(str(folder)), None)


def _read_ini(ini: Path, key: str) -> str:
    buf = ctypes.create_unicode_buffer(2048)
    ctypes.windll.kernel32.GetPrivateProfileStringW(SECTION, key, "", buf, len(buf), str(ini))
    return buf.value


def _ini_has_other_settings(ini: Path) -> bool:
    """desktop.ini 除了圖示之外還有沒有其他設定（例如 LocalizedResourceName、其他段落）。"""
    try:
        raw = ini.read_bytes()
    except OSError:
        return False
    text = raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw.decode("mbcs", "replace")
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(";") or line.lower() == f"[{SECTION.lower()}]":
            continue
        if line.startswith("[") or line.split("=", 1)[0].strip().lower() not in ("iconresource", "iconfile",
                                                                                  "iconindex"):
            return True
    return False


# ---------------------------------------------------------------- 對外的功能
def current_cover(folder: str | Path) -> str:
    """目前設定的圖示（desktop.ini 的 IconResource 或 IconFile）；沒有就回傳空字串。"""
    _require_windows()
    ini = Path(folder) / "desktop.ini"
    if not ini.exists():
        return ""
    return _read_ini(ini, "IconResource") or _read_ini(ini, "IconFile")


def apply_cover(folder: str | Path, image_path: str | Path, mode: str = MODE_CROP) -> Path:
    """把 image_path 設成 folder 的圖示，回傳產生的 ico 路徑。"""
    _require_windows()
    folder = Path(folder).resolve()
    if not folder.is_dir():
        raise CoverError(f"不是資料夾：{folder}")
    icon = make_icon(image_path, folder / ICON_NAME, mode)
    fcs = SHFOLDERCUSTOMSETTINGS()
    fcs.dwSize = ctypes.sizeof(SHFOLDERCUSTOMSETTINGS)
    fcs.dwMask = FCSM_ICONFILE
    fcs.pszIconFile = ICON_NAME          # 相對路徑：資料夾搬家也不會失效
    fcs.iIconIndex = 0
    hr = ctypes.windll.shell32.SHGetSetFolderCustomSettings(ctypes.byref(fcs), str(folder), FCS_FORCEWRITE)
    if hr != 0:
        raise CoverError(f"Windows 拒絕修改這個資料夾的設定（HRESULT 0x{hr & 0xFFFFFFFF:08X}）：{folder}")
    _set_attributes(icon, FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM)
    ini = folder / "desktop.ini"
    _set_attributes(ini, _get_attributes(ini) | FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM)
    _notify(folder)
    return icon


def remove_cover(folder: str | Path) -> None:
    """恢復成預設的資料夾圖示。desktop.ini 有其他設定就只拿掉圖示那幾行。"""
    _require_windows()
    folder = Path(folder).resolve()
    ini = folder / "desktop.ini"
    if ini.exists():
        for key in ("IconResource", "IconFile", "IconIndex"):
            ctypes.windll.kernel32.WritePrivateProfileStringW(SECTION, key, None, str(ini))
        if not _ini_has_other_settings(ini):
            _set_attributes(ini, 0)
            ini.unlink()
            # 沒有自訂設定了：拿掉資料夾的唯讀／系統屬性（SHGetSetFolderCustomSettings 加上去的）
            ctypes.windll.shlwapi.PathUnmakeSystemFolderW(str(folder))
    icon = folder / ICON_NAME
    if icon.exists():
        _set_attributes(icon, 0)
        icon.unlink()
    _notify(folder)
