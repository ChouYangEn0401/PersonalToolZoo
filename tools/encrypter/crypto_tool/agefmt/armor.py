"""age 的 ASCII armor：RFC 7468 第 3 節的嚴格 PEM，標籤 ``AGE ENCRYPTED FILE``。

讀取規則（照規格與參考實作）：
* 開頭行之前、結尾行之後只允許空白（各最多 1024 個位元組）；
* 行尾可以是 LF 或 CRLF；行內不能有其他 CR；
* 每行最多 64 字，只有最後一行可以比較短，不能有空行、不能有 PEM 標頭；
* base64 要有 padding 且是正規形式；最後一行之後必須緊接結尾行。

寫出時：開頭行、每 64 字一行、結尾行，全部用 LF。
"""

from __future__ import annotations

import base64
import re

from ._common import armor_error, b64_decode_padded
from .header import BYTES_PER_LINE, COLUMNS, Source

BEGIN = b"-----BEGIN AGE ENCRYPTED FILE-----"
END = b"-----END AGE ENCRYPTED FILE-----"
MAX_WHITESPACE = 1024
_MAX_LINE = 4096
_WS = b" \t\n\r\x0b\x0c"
_FULL_LINES = re.compile(rb"(?:[A-Za-z0-9+/]{64}\r?\n)+")


def looks_armored(head: bytes) -> bool:
    """去掉開頭空白（最多 1024 位元組）後是不是以 ``-----BEGIN`` 開始。"""
    stripped = head[:MAX_WHITESPACE + len(BEGIN)].lstrip(_WS)
    return stripped.startswith(b"-----")


class ArmorReader:
    """把 armor 文字一邊讀一邊解成二進位；有 ``read(n)``，可以再包進 Source。"""

    def __init__(self, raw):
        self._src = Source(raw)
        self._pending = b""
        self._gen = self._lines()
        self._done = False

    def read(self, n: int = -1) -> bytes:
        out = bytearray()
        while n < 0 or len(out) < n:
            if not self._pending:
                if self._done:
                    break
                try:
                    self._pending = next(self._gen)
                except StopIteration:
                    self._done = True
                    break
            take = len(self._pending) if n < 0 else n - len(out)
            out += self._pending[:take]
            self._pending = self._pending[take:]
        return bytes(out)

    def _get_line(self) -> bytes:
        line = self._src.readline(_MAX_LINE)
        if not line:
            raise armor_error("unexpected-eof")
        if not line.endswith(b"\n") and len(line) >= _MAX_LINE:
            raise armor_error("line-too-long")
        if line.endswith(b"\n"):
            line = line[:-1]
        if line.endswith(b"\r"):
            line = line[:-1]
        return line

    def _drain_trailing(self) -> None:
        rest = self._src.read(MAX_WHITESPACE)
        if rest.strip(_WS):
            raise armor_error("trailing-data")
        if len(rest) == MAX_WHITESPACE:
            raise armor_error("too-much-trailing-whitespace")

    def _lines(self):
        removed = 0
        while True:
            line = self._get_line()
            if not line.strip(_WS):
                removed += len(line) + 1
                if removed > MAX_WHITESPACE:
                    raise armor_error("too-much-leading-whitespace")
                continue
            if line != BEGIN:
                raise armor_error("invalid-first-line")
            break
        while True:
            # 快速路徑：連續的「64 個 base64 字元＋換行」整批一起解。這種行剛好 48 位元組、
            # 一定是正規形式，跟逐行檢查的結果相同，只是快很多。
            full = _FULL_LINES.match(self._src.peek(1 << 16))
            if full:
                raw = self._src.read(full.end())
                yield base64.b64decode(raw.translate(None, b"\r\n"))
                continue
            line = self._get_line()
            if line == END:
                self._drain_trailing()
                return
            if not line:
                raise armor_error("empty-line")
            if len(line) > COLUMNS:
                raise armor_error("line-too-long")
            if b"\r" in line or b"\n" in line:
                raise armor_error("stray-newline")
            try:
                data = b64_decode_padded(line)
            except ValueError:
                raise armor_error("bad-base64") from None
            if len(data) < BYTES_PER_LINE:
                # 短行一定是最後一行：先確認緊接著結尾行，再把資料交出去
                if self._get_line() != END:
                    raise armor_error("invalid-closing-line")
                self._drain_trailing()
                yield data
                return
            yield data


class ArmorWriter:
    """把二進位一邊寫一邊編成 armor。寫完一定要呼叫 ``close()``（不會關掉底下的檔案）。"""

    def __init__(self, dst):
        self._dst = dst
        self._pending = bytearray()
        self._closed = False
        self.written = 0
        self._emit(BEGIN + b"\n")

    def _emit(self, data: bytes) -> None:
        self._dst.write(data)
        self.written += len(data)

    def write(self, data: bytes) -> int:
        if self._closed:
            raise ValueError("ArmorWriter already closed")
        self._pending += data
        full = len(self._pending) // BYTES_PER_LINE * BYTES_PER_LINE
        if full:
            enc = base64.b64encode(bytes(self._pending[:full]))
            del self._pending[:full]
            self._emit(b"".join(enc[i:i + COLUMNS] + b"\n" for i in range(0, len(enc), COLUMNS)))
        return len(data)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._pending:
            self._emit(base64.b64encode(bytes(self._pending)) + b"\n")
            self._pending.clear()
        self._emit(END + b"\n")
