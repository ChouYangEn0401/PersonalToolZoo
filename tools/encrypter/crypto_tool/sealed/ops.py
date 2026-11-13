"""ISD2 預覽格式（已停用）：解密、看資訊。

這個格式是 0.4.0 之前在開發線上做過、從沒發版的自有格式；0.4.0 起**只能解密，不能再產生**
（命令列與視窗都沒有產生它的選項）。產生樣本的函式改名為 ``_encrypt_preview_for_tests``，
只給測試做解密用的樣本。現行的加密見 workflow.py（age／OpenPGP）。

原則：
* 輸出先寫到目標旁邊的暫存檔，全部成功才改名成目標；中途失敗會把暫存檔刪掉，
  所以不會留下半個檔案，也不會留下沒通過驗證的明文。
* 目標已存在就拒絕，除非呼叫端明確要求覆蓋；已存在且非空的資料夾永遠不覆蓋。
* 資料夾內容是 tar；解開時只收一般檔案與資料夾，路徑檢查與 packing.py 共用。
"""

from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import tarfile
from pathlib import Path
from typing import Callable

from .container import (
    DEFAULT_CHUNK_SIZE, EXTENSION, HEADER_LEN, PAYLOAD_FILE, PAYLOAD_TAR,
    KeyMaterial, SealReader, SealWriter, parse_header,
)
from .errors import SealError
from .packing import safe_member_path as _safe_member_path
from .packing import walk as _walk

Progress = Callable[[int, int], None]
_COPY_BLOCK = 1024 * 1024
_TAR_SUFFIX = ".tar"


def _default_preview_output(src: str | os.PathLike) -> Path:
    p = Path(src)
    return p.with_name(p.name + EXTENSION)


def default_decrypt_output(src: str | os.PathLike) -> Path | None:
    """加密檔名去掉 .isd2；檔名不是 .isd2 結尾就沒有預設值（回傳 None）。"""
    p = Path(src)
    if p.name.lower().endswith(EXTENSION) and len(p.name) > len(EXTENSION):
        return p.with_name(p.name[: -len(EXTENSION)])
    return None


def _temp_beside(dst: Path) -> Path:
    return dst.with_name(f".{dst.name}.partial-{secrets.token_hex(4)}")


def _sync(fileobj) -> None:
    """改名之前先確定內容真的寫到磁碟了（斷電時不會留下一個名字對、內容不全的檔）。"""
    fileobj.flush()
    try:
        os.fsync(fileobj.fileno())
    except OSError:  # 少數檔案系統不支援
        pass


def _remove(path: Path) -> None:
    try:
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink()
    except OSError:
        pass


def _check_target(dst: Path, force: bool) -> None:
    if not dst.parent.is_dir():
        raise SealError("input_missing", "輸出位置的資料夾不存在。",
                        action="先建立資料夾，或換一個輸出位置。")
    if dst.is_dir():
        if any(dst.iterdir()):
            raise SealError(
                "output_exists", "輸出位置已經有一個非空的資料夾，沒有覆蓋。",
                action="換一個輸出位置（-o）；資料夾不會被覆蓋，即使加了 --force。",
            )
    elif dst.exists() and not force:
        raise SealError(
            "output_exists", "輸出檔已經存在，沒有覆蓋。",
            action="換一個輸出位置（-o），或確定要覆蓋時加 --force。",
        )


def _commit(tmp: Path, dst: Path, force: bool) -> None:
    """把暫存檔／暫存資料夾改名成目標。沒有 force 時，目標在這期間冒出來也不會被蓋掉。"""
    if dst.is_dir():
        dst.rmdir()  # _check_target 已確認是空的；不是空的這裡會失敗
    if tmp.is_dir() or force:
        os.replace(tmp, dst)
        return
    if os.name == "nt":
        os.rename(tmp, dst)  # Windows：目標存在會失敗
        return
    try:
        os.link(tmp, dst)  # 目標存在會失敗
        tmp.unlink()
    except FileExistsError:
        raise
    except OSError:  # 檔案系統不支援硬連結
        if dst.exists():
            raise FileExistsError(str(dst))
        os.rename(tmp, dst)


def _run(tmp: Path, dst: Path, force: bool, work: Callable[[], None]) -> None:
    try:
        work()
        _commit(tmp, dst, force)
    except SealError:
        _remove(tmp)
        raise
    except FileExistsError:
        _remove(tmp)
        raise SealError("output_exists", "輸出檔已經存在，沒有覆蓋。",
                        action="換一個輸出位置（-o）。") from None
    except tarfile.TarError as exc:
        _remove(tmp)
        raise SealError("corrupt", "解開後的資料夾封存內容不正確。",
                        detail=type(exc).__name__) from None
    except OSError as exc:
        _remove(tmp)
        raise SealError(
            "io_error", "讀寫檔案失敗（權限不足、磁碟滿了，或檔案正被別的程式使用）。",
            detail=type(exc).__name__,
        ) from None
    except BaseException:
        _remove(tmp)
        raise


def _encrypt_preview_for_tests(
    src: str | os.PathLike,
    dst: str | os.PathLike | None,
    material: KeyMaterial,
    *,
    cipher: str = "aes-256-gcm",
    force: bool = False,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    progress: Progress | None = None,
    **writer_options,
) -> dict:
    """**只給測試用**：產生 ISD2 預覽格式（已停用）的樣本，用來測試「舊檔仍解得開」。

    產品程式（命令列、視窗）不得呼叫；0.4.0 起只產生 age 與 OpenPGP。
    """
    src_p = Path(src)
    if not src_p.exists():
        raise SealError("input_missing", "找不到要加密的檔案或資料夾。")
    is_dir = src_p.is_dir()
    if not is_dir and not src_p.is_file():
        raise SealError("bad_input", "只能加密一般的檔案或資料夾。")
    dst_p = Path(dst) if dst else _default_preview_output(src_p)
    src_abs, dst_abs = src_p.resolve(), dst_p.resolve()
    if dst_abs == src_abs:
        raise SealError("bad_input", "輸出位置不能跟輸入是同一個。")
    if is_dir and src_abs in dst_abs.parents:
        raise SealError("bad_input", "輸出檔不能放在要加密的資料夾裡面。",
                        action="用 -o 指定資料夾外面的位置。")
    if dst_p.is_dir():
        raise SealError("output_exists", "輸出位置是一個已存在的資料夾。",
                        action="用 -o 指定一個檔名。")
    _check_target(dst_p, force)

    result = {"action": "encrypt", "input": str(src_p), "output": str(dst_p),
              "payload": "folder" if is_dir else "file", "cipher": cipher}
    tmp = _temp_beside(dst_p)

    def work() -> None:
        with open(tmp, "wb") as out:
            writer = SealWriter(
                out, material, aead=cipher, chunk_size=chunk_size,
                payload=PAYLOAD_TAR if is_dir else PAYLOAD_FILE, **writer_options,
            )
            result["kdf"] = writer.header.describe()["kdf"]
            if is_dir:
                items, skipped = _walk(src_p)
                total = sum(p.stat().st_size for p, _ in items if p.is_file())
                done = 0
                files = 0
                with tarfile.open(fileobj=writer, mode="w|", format=tarfile.PAX_FORMAT) as tar:
                    for path, arcname in items:
                        info = tar.gettarinfo(str(path), arcname)
                        # 不把帳號名稱、擁有者編號寫進封存
                        info.uid = info.gid = 0
                        info.uname = info.gname = ""
                        if info.isdir():
                            tar.addfile(info)
                            continue
                        with open(path, "rb") as fh:
                            tar.addfile(info, fh)
                        files += 1
                        done += info.size
                        if progress:
                            progress(done, total)
                result["files"] = files
                result["skipped_links"] = skipped
                result["bytes_in"] = total
            else:
                total = src_p.stat().st_size
                done = 0
                with open(src_p, "rb") as fh:
                    while True:
                        block = fh.read(_COPY_BLOCK)
                        if not block:
                            break
                        writer.write(block)
                        done += len(block)
                        if progress:
                            progress(done, total)
                result["bytes_in"] = done
            writer.close()
            _sync(out)
        result["bytes_out"] = tmp.stat().st_size

    _run(tmp, dst_p, force, work)
    return result


def _extract(reader: SealReader, out_dir: Path, progress: Progress | None, total: int) -> int:
    files = 0
    out_dir.mkdir()
    with tarfile.open(fileobj=reader, mode="r|") as tar:
        for member in tar:
            target = _safe_member_path(out_dir, member.name)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif member.isreg():
                target.parent.mkdir(parents=True, exist_ok=True)
                source = tar.extractfile(member)
                with open(target, "wb") as fh:
                    shutil.copyfileobj(source, fh, _COPY_BLOCK)
                try:
                    os.utime(target, (member.mtime, member.mtime))
                except (OSError, OverflowError, ValueError):
                    pass
                files += 1
            else:
                raise SealError(
                    "unsafe_archive",
                    "封存裡有連結或特殊檔案，已停止，沒有輸出任何內容。",
                    action="向提供檔案的人確認來源。",
                )
            if progress:
                progress(min(reader_position(reader), total), total)
    reader.drain()
    return files


def reader_position(reader: SealReader) -> int:
    try:
        return reader._in.tell()
    except (OSError, AttributeError):
        return 0


def decrypt_path(
    src: str | os.PathLike,
    dst: str | os.PathLike | None,
    material: KeyMaterial,
    *,
    force: bool = False,
    keep_tar: bool = False,
    progress: Progress | None = None,
) -> dict:
    src_p = Path(src)
    if not src_p.is_file():
        raise SealError("input_missing", "找不到要解密的檔案。")
    with open(src_p, "rb") as fh:
        header = parse_header(fh.read(HEADER_LEN))
    is_folder = header.payload == PAYLOAD_TAR

    if dst:
        dst_p = Path(dst)
    else:
        dst_p = default_decrypt_output(src_p)
        if dst_p is None:
            raise SealError("bad_input", "加密檔的檔名不是 .isd2 結尾，無法決定輸出檔名。",
                            action="用 -o 指定輸出位置。")
        if is_folder and keep_tar:
            dst_p = dst_p.with_name(dst_p.name + _TAR_SUFFIX)
    if dst_p.resolve() == src_p.resolve():
        raise SealError("bad_input", "輸出位置不能跟輸入是同一個。")
    as_dir = is_folder and not keep_tar
    if not as_dir and dst_p.is_dir():
        raise SealError("output_exists", "輸出位置是一個已存在的資料夾。",
                        action="用 -o 指定一個檔名。")
    if as_dir and dst_p.exists() and not dst_p.is_dir():
        raise SealError("output_exists", "要解成資料夾，但輸出位置已經有同名的檔案。",
                        action="換一個輸出位置（-o）。")
    _check_target(dst_p, force)

    total = src_p.stat().st_size
    result = {"action": "decrypt", "input": str(src_p), "output": str(dst_p),
              "payload": "folder" if as_dir else ("tar" if is_folder else "file"),
              "cipher": header.describe()["cipher"], "kdf": header.describe()["kdf"]}
    tmp = _temp_beside(dst_p)

    def work() -> None:
        with open(src_p, "rb") as fh:
            reader = SealReader(fh, material)
            if as_dir:
                result["files"] = _extract(reader, tmp, progress, total)
                return
            written = 0
            with open(tmp, "wb") as out:
                while True:
                    block = reader.read(_COPY_BLOCK)
                    if not block:
                        break
                    out.write(block)
                    written += len(block)
                    if progress:
                        progress(min(fh.tell(), total), total)
                _sync(out)
            result["bytes_out"] = written

    _run(tmp, dst_p, force, work)
    return result


_LEGACY_NOTE_RE = re.compile(rb'NOTE="""(.*?)"""', re.DOTALL)


def info_path(src: str | os.PathLike) -> dict:
    """不需要金鑰就能看的資訊：格式、加密法、內容種類。不解密、不顯示檔名以外的內容。"""
    src_p = Path(src)
    if not src_p.is_file():
        raise SealError("input_missing", "找不到檔案。")
    size = src_p.stat().st_size
    try:
        with open(src_p, "rb") as fh:
            head = fh.read(HEADER_LEN)
            try:
                header = parse_header(head)
            except SealError as exc:
                if exc.code != "legacy_format":
                    raise
                return _legacy_info(src_p, size)
    except OSError as exc:
        raise SealError("io_error", "讀不到檔案。", detail=type(exc).__name__) from None
    data = {"action": "info", "input": str(src_p), "size": size}
    data.update(header.describe())
    return data


def _legacy_info(src_p: Path, size: int) -> dict:
    data = {"action": "info", "input": str(src_p), "size": size, "format": "isd-legacy",
            "note": "舊版格式；命令列不解密，請用視窗程式的舊版工具。"}
    if size <= 256 * 1024 * 1024:
        match = _LEGACY_NOTE_RE.search(src_p.read_bytes())
        if match:
            try:
                note = json.loads(match.group(1).decode("utf-8"))
                for key in ("algorithm", "mode", "iterations"):
                    if isinstance(note.get(key), (str, int)):
                        data["legacy_" + key] = note[key]
            except (ValueError, UnicodeDecodeError):
                pass
    return data
