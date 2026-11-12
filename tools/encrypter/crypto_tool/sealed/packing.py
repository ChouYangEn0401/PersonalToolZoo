"""把一個或多個輸入（檔案、資料夾）打包成 tar，以及安全地解開 tar。

* 打包是「產生器」：一塊一塊吐出標準的 PAX tar 位元組，可以直接餵給 age 加密（明文 tar 不落地），
  PGP 模式則寫成暫存檔交給 gpg（gpg 只吃檔案）。
* 不跟著連結走：捷徑、符號連結、特殊檔案都略過並計數（``skipped_links``）。
* 封存裡不放帳號名稱與擁有者編號。
* 一個資料夾：成員是資料夾「裡面」的東西（跟 ISD2 預覽格式相同，解開後還原成那個資料夾）；
  多個輸入：每個輸入用自己的名字當最上層（``a.txt``、``photos/…``）。
* 解開時只接受一般檔案與資料夾，路徑必須在輸出資料夾底下，Windows 的保留名稱（CON、NUL…）也拒絕；
  其他情況整個拒絕（``unsafe_archive``），呼叫端負責刪掉解到一半的暫存資料夾。
"""

from __future__ import annotations

import os
import re
import shutil
import tarfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Callable, Iterator

from .errors import SealError
from .ops import _is_junction, _walk

Progress = Callable[[int, int], None]
BLOCK = tarfile.BLOCKSIZE              # 512
RECORD = tarfile.RECORDSIZE            # 10240，tarfile 寫串流時也補到這個倍數
_READ = 1024 * 1024
_WINDOWS_BAD = re.compile(r'[<>:"|?*\x00-\x1f]')
_RESERVED = re.compile(r"^(CON|PRN|AUX|NUL|COM[0-9¹²³]|LPT[0-9¹²³])(\..*)?$", re.IGNORECASE)


@dataclass
class Plan:
    """要打包的東西。``single_file`` 有值時不需要打包。"""

    inputs: list[Path]
    single_file: Path | None = None
    items: list[tuple[Path, str]] = field(default_factory=list)
    skipped_links: int = 0
    total_bytes: int = 0
    files: int = 0

    @property
    def is_archive(self) -> bool:
        return self.single_file is None


def plan(inputs) -> Plan:
    """檢查輸入並列出要打包的項目（固定順序）。"""
    paths = [Path(p) for p in inputs]
    if not paths:
        raise SealError("bad_input", "沒有指定要加密的檔案或資料夾。")
    for p in paths:
        if p.is_symlink() or _is_junction(p):
            raise SealError("bad_input", "輸入是一個捷徑或連結；請直接選它指向的檔案或資料夾。")
        if not p.exists():
            raise SealError("input_missing", "找不到要加密的檔案或資料夾。")
        if not (p.is_file() or p.is_dir()):
            raise SealError("bad_input", "只能加密一般的檔案或資料夾。")
    resolved = [p.resolve() for p in paths]
    if len(set(resolved)) != len(resolved):
        raise SealError("bad_input", "同一個檔案或資料夾被指定了兩次。")
    if len(paths) == 1 and paths[0].is_file():
        return Plan(paths, single_file=paths[0], total_bytes=paths[0].stat().st_size, files=1)

    result = Plan(paths)
    if len(paths) == 1:
        items, skipped = _walk(paths[0])
        result.items = items
        result.skipped_links = skipped
    else:
        seen: set[str] = set()
        for p in paths:
            top = p.name
            if not top or top.casefold() in seen:
                raise SealError("bad_input", "有兩個輸入的名稱一樣，打包後會互相蓋掉。",
                                action="把其中一個改名，或放進同一個資料夾再加密那個資料夾。")
            seen.add(top.casefold())
            result.items.append((p, top))
            if p.is_dir():
                items, skipped = _walk(p)
                result.items.extend((child, f"{top}/{rel}") for child, rel in items)
                result.skipped_links += skipped
    for path, _name in result.items:
        if path.is_file():
            result.files += 1
            result.total_bytes += path.stat().st_size
    return result


def check_output_outside(p: Plan, output: Path) -> None:
    out = output.resolve()
    for src in p.inputs:
        src_abs = src.resolve()
        if out == src_abs:
            raise SealError("bad_input", "輸出位置不能跟輸入是同一個。")
        if src.is_dir() and src_abs in out.parents:
            raise SealError("bad_input", "輸出檔不能放在要加密的資料夾裡面。",
                            action="用 -o 指定資料夾外面的位置。")


def _header(path: Path, name: str) -> tarfile.TarInfo:
    st = path.stat()
    info = tarfile.TarInfo(name)
    info.mtime = int(st.st_mtime)
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    if path.is_dir():
        info.type = tarfile.DIRTYPE
        info.mode = 0o755
        info.size = 0
    else:
        info.type = tarfile.REGTYPE
        info.mode = 0o644
        info.size = st.st_size
    return info


def iter_tar(p: Plan, progress: Progress | None = None) -> Iterator[bytes]:
    """依 ``plan`` 一塊一塊產生標準 PAX tar 的位元組。檔案在途中變大變小就停止（不打包不一致的內容）。"""
    done = 0
    written = 0
    for path, name in p.items:
        info = _header(path, name)
        head = info.tobuf(tarfile.PAX_FORMAT, "utf-8", "surrogateescape")
        written += len(head)
        yield head
        if info.type == tarfile.DIRTYPE:
            continue
        remaining = info.size
        with open(path, "rb") as fh:
            while remaining:
                block = fh.read(min(_READ, remaining))
                if not block:
                    break
                remaining -= len(block)
                written += len(block)
                done += len(block)
                yield block
                if progress:
                    progress(done, p.total_bytes)
            if remaining or fh.read(1):
                raise SealError("io_error", "有檔案在加密途中被改了（大小變了），已停止。",
                                action="等檔案不再被寫入（例如關掉正在用它的程式）後再試。",
                                detail="size-changed")
        pad = (-info.size) % BLOCK
        if pad:
            written += pad
            yield b"\0" * pad
    end = b"\0" * (2 * BLOCK)
    written += len(end)
    tail = (-written) % RECORD
    yield end + b"\0" * tail


class IterReader:
    """把產生器變成有 ``read(n)`` 的物件（給 age 的 encrypt_stream）。"""

    def __init__(self, chunks):
        self._it = iter(chunks)
        self._buf = bytearray()
        self._done = False

    def read(self, n: int = -1) -> bytes:
        while not self._done and (n < 0 or len(self._buf) < n):
            try:
                self._buf += next(self._it)
            except StopIteration:
                self._done = True
        if n < 0:
            out = bytes(self._buf)
            self._buf.clear()
            return out
        out = bytes(self._buf[:n])
        del self._buf[:n]
        return out


def write_tar(p: Plan, fileobj, progress: Progress | None = None) -> None:
    for chunk in iter_tar(p, progress):
        fileobj.write(chunk)


def is_tar(path: Path) -> bool:
    """看內容是不是 tar（POSIX ustar／GNU 標記）。只看檔頭，不信任副檔名。"""
    try:
        with open(path, "rb") as fh:
            head = fh.read(BLOCK)
    except OSError:
        return False
    if len(head) < BLOCK or head[257:262] != b"ustar":
        return False
    try:
        tarfile.TarInfo.frombuf(head, "utf-8", "surrogateescape")
    except tarfile.HeaderError:
        return False
    return True


def safe_member_path(root: Path, name: str) -> Path:
    """封存裡的名稱只能是資料夾底下的相對路徑；其他一律拒絕。"""
    pure = PurePosixPath(name)
    parts = pure.parts
    bad = (not name or "\\" in name or pure.is_absolute() or not parts
           or any(part in ("..", ".") or _WINDOWS_BAD.search(part) or _RESERVED.match(part)
                  or part != part.rstrip(". ") for part in parts))
    if bad:
        raise SealError(
            "unsafe_archive",
            "封存裡有不安全的檔名（想寫到資料夾外面，或是系統保留的名稱），已停止，沒有輸出任何內容。",
            action="不要再開這個檔案；向提供檔案的人確認來源。",
        )
    return root.joinpath(*parts)


def extract_tar(tar_path: Path, out_dir: Path, progress: Progress | None = None) -> int:
    """把 tar 安全地解到 ``out_dir``（不能已存在）。回傳檔案數。失敗時呼叫端要刪掉 ``out_dir``。"""
    total = tar_path.stat().st_size
    files = 0
    out_dir.mkdir()
    with open(tar_path, "rb") as raw, tarfile.open(fileobj=raw, mode="r|") as tar:
        for member in tar:
            target = safe_member_path(out_dir, member.name)
            if member.isdir():
                if target.exists() and not target.is_dir():
                    raise SealError("unsafe_archive", "封存裡同一個名稱同時是檔案和資料夾，已停止。")
                target.mkdir(parents=True, exist_ok=True)
            elif member.isreg():
                if target.is_dir():
                    raise SealError("unsafe_archive", "封存裡同一個名稱同時是檔案和資料夾，已停止。")
                target.parent.mkdir(parents=True, exist_ok=True)
                source = tar.extractfile(member)
                with open(target, "wb") as fh:
                    shutil.copyfileobj(source, fh, _READ)
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
                try:
                    progress(min(raw.tell(), total), total)
                except OSError:
                    pass
    return files


def remove_tree(path: Path) -> None:
    try:
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path, ignore_errors=True)
        elif path.exists() or path.is_symlink():
            path.unlink()
    except OSError:
        pass
