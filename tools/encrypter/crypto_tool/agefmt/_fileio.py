"""輸出檔的原子寫入：先寫到目標旁邊的暫存檔、fsync，全部成功才改名成目標。

失敗（包括驗證失敗、使用者中斷）一律刪掉暫存檔，不留半成品，也不留沒驗證過的明文。
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Callable

from ._common import fail
from ..sealed.errors import SealError


def as_path(p, what: str) -> Path:
    if not isinstance(p, (str, os.PathLike)) or str(p) == "":
        raise fail("bad_input", f"{what}路徑不正確。")
    return Path(p)


def check_input(src: Path) -> int:
    if not src.exists():
        raise fail("input_missing", "找不到輸入檔。", "確認路徑是否正確。")
    if not src.is_file():
        raise fail("bad_input", "輸入必須是一般檔案（不能是資料夾）。")
    return src.stat().st_size


def check_output(dst: Path, overwrite: bool) -> None:
    if not dst.parent.is_dir():
        raise fail("input_missing", "輸出位置的資料夾不存在。", "先建立資料夾，或換一個輸出位置。")
    if dst.is_dir():
        raise fail("output_exists", "輸出位置是一個資料夾，沒有覆蓋。", "換一個輸出檔名。")
    if dst.exists() and not overwrite:
        raise fail("output_exists", "輸出檔已經存在，沒有覆蓋。", "換一個輸出位置，或確定要覆蓋時明確要求覆蓋。")


def same_file(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b.resolve() or (b.exists() and os.path.samefile(a, b))
    except OSError:
        return False


def _temp_beside(dst: Path) -> Path:
    return dst.with_name(f".{dst.name}.partial-{secrets.token_hex(4)}")


def _remove(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


def _commit(tmp: Path, dst: Path, overwrite: bool) -> None:
    if overwrite:
        os.replace(tmp, dst)
        return
    if os.name == "nt":
        os.rename(tmp, dst)          # Windows：目標存在時會失敗，不會蓋掉
        return
    try:
        os.link(tmp, dst)            # POSIX：目標存在時會失敗
        tmp.unlink()
    except FileExistsError:
        raise
    except OSError:                  # 不支援硬連結的檔案系統
        if dst.exists():
            raise FileExistsError(str(dst))
        os.rename(tmp, dst)


def atomic_write(dst: Path, overwrite: bool, work: Callable[[object], object],
                 before_commit: Callable[[], None] | None = None):
    """在暫存檔上執行 ``work(fileobj)``，成功才改名成 dst；回傳 work 的結果。"""
    tmp = _temp_beside(dst)
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
        fd = os.open(tmp, flags, 0o600)   # 解密結果與身分檔都只給自己讀
        with os.fdopen(fd, "wb") as fh:
            result = work(fh)
            fh.flush()
            try:
                os.fsync(fh.fileno())
            except OSError:  # 少數檔案系統不支援
                pass
        if before_commit:
            before_commit()
        _commit(tmp, dst, overwrite)
        return result
    except SealError:
        _remove(tmp)
        raise
    except FileExistsError:
        _remove(tmp)
        raise fail("output_exists", "輸出檔已經存在，沒有覆蓋。",
                   "換一個輸出位置，或確定要覆蓋時明確要求覆蓋。") from None
    except OSError as exc:
        _remove(tmp)
        raise fail("io_error", "讀寫檔案失敗（權限不足、磁碟滿了，或檔案正被別的程式使用）。",
                   "確認磁碟空間與權限後再試。", type(exc).__name__) from None
    except BaseException:
        _remove(tmp)
        raise
