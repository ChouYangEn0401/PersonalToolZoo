"""age v1 標頭：解析（嚴格）與序列化。

    age-encryption.org/v1
    -> X25519 <base64 臨時公鑰>
    <base64 本體，每行 64 字，最後一行一定短於 64 字（可以是空行）>
    --- <base64 HMAC-SHA-256>

MAC 的範圍是「從第一個位元組到 ``---`` 為止（不含後面的空白）」，
鍵是 HKDF-SHA-256(ikm=file key, salt=空, info="header")。

解析規則照規格的 ABNF 與參考實作：引數只能是 1 個以上的可見 ASCII（33～126），
用單一空白分隔；base64 必須無 padding 且是正規形式；任何 CR 都會被拒絕。
因為解析是嚴格的，重新序列化會得到一模一樣的位元組，MAC 就用重新序列化的結果算。
"""

from __future__ import annotations

from dataclasses import dataclass

from ._common import b64_decode_raw, b64_encode_raw, consteq, fail, header_error, hkdf_sha256, hmac_sha256

INTRO = b"age-encryption.org/v1\n"
VERSION_PREFIX = b"age-encryption.org/"
STANZA_PREFIX = b"->"
FOOTER_PREFIX = b"---"
COLUMNS = 64
BYTES_PER_LINE = COLUMNS // 4 * 3      # 48
MAX_HEADER_BYTES = 2 << 20             # 參考實作的上限：2 MiB
MAX_STANZAS = 1024                     # 參考實作的上限
MAX_ARGS = 128                         # 參考實作的上限
MAC_SIZE = 32


def _valid_arg(a: bytes) -> bool:
    return len(a) > 0 and all(33 <= c <= 126 for c in a)


@dataclass(frozen=True)
class Stanza:
    """一個收件人區塊。``type`` 是第一個引數，``args`` 是其餘引數。"""

    type: str
    args: tuple[str, ...]
    body: bytes

    def marshal(self) -> bytes:
        parts = [self.type, *self.args]
        for p in parts:
            if not isinstance(p, str) or not p.isascii() or not _valid_arg(p.encode("ascii")):
                raise ValueError("invalid stanza argument")
        out = bytearray(STANZA_PREFIX + b" " + " ".join(parts).encode("ascii") + b"\n")
        enc = b64_encode_raw(self.body)
        for i in range(0, len(enc), COLUMNS):
            out += enc[i:i + COLUMNS] + b"\n"
        if len(enc) % COLUMNS == 0:  # 最後一行必須短於 64 字：補一個空行
            out += b"\n"
        return bytes(out)

    def __repr__(self) -> str:  # 本體是密文，不印出來
        return f"Stanza(type={self.type!r}, args={len(self.args)}, body={len(self.body)} bytes)"


@dataclass(frozen=True)
class Header:
    stanzas: tuple[Stanza, ...]
    mac: bytes = b""

    def marshal_without_mac(self) -> bytes:
        if not self.stanzas:
            raise ValueError("no recipient stanzas")
        return INTRO + b"".join(s.marshal() for s in self.stanzas) + FOOTER_PREFIX

    def marshal(self) -> bytes:
        if len(self.mac) != MAC_SIZE:
            raise ValueError("header MAC missing")
        return self.marshal_without_mac() + b" " + b64_encode_raw(self.mac) + b"\n"

    @property
    def stanza_types(self) -> tuple[str, ...]:
        return tuple(s.type for s in self.stanzas)


def header_mac(file_key: bytes, header: Header) -> bytes:
    key = hkdf_sha256(file_key, b"", b"header")
    return hmac_sha256(key, header.marshal_without_mac())


def seal_header(file_key: bytes, stanzas) -> Header:
    h = Header(tuple(stanzas))
    return Header(h.stanzas, header_mac(file_key, h))


def verify_mac(file_key: bytes, header: Header) -> None:
    if not consteq(header_mac(file_key, header), header.mac):
        raise fail(
            "corrupt",
            "age 檔的標頭被改過或損壞（標頭驗證碼不符）。",
            "確認拿到的是完整、沒被改過的原始檔；如果有備份，改用備份。",
            "hmac",
        )


class Source:
    """包住二進位讀取物件：可以 peek、讀一行（有上限）、讀滿 n 個位元組。

    標頭與內容共用同一個 Source，所以不會多讀或少讀。``consumed`` 是已交出去的位元組數。
    """

    def __init__(self, raw, block: int = 1 << 16):
        self._raw = raw
        self._buf = bytearray()
        self._pos = 0          # _buf 裡還沒交出去的資料從這裡開始
        self._eof = False
        self._block = block
        self.consumed = 0

    def _avail(self) -> int:
        return len(self._buf) - self._pos

    def _fill(self, n: int) -> None:
        while self._avail() < n and not self._eof:
            if self._pos:  # 需要更多資料時才把已交出去的部分丟掉（避免每讀一行就搬一次）
                del self._buf[:self._pos]
                self._pos = 0
            chunk = self._raw.read(max(n - self._avail(), self._block))
            if not chunk:
                self._eof = True
            else:
                self._buf += chunk

    def peek(self, n: int) -> bytes:
        self._fill(n)
        return bytes(self._buf[self._pos:self._pos + n])

    def read(self, n: int) -> bytes:
        """讀滿 n 個位元組；只有遇到檔尾才會少於 n。"""
        self._fill(n)
        out = bytes(self._buf[self._pos:self._pos + n])
        self._pos += len(out)
        self.consumed += len(out)
        return out

    def readline(self, limit: int) -> bytes:
        """讀到第一個換行（含）為止，最多 limit 個位元組；檔尾時回傳剩下的。"""
        searched = 0
        while True:
            end = min(self._pos + limit, len(self._buf))
            i = self._buf.find(b"\n", self._pos + searched, end)
            if i >= 0:
                return self.read(i + 1 - self._pos)
            if self._avail() >= limit or self._eof:
                return self.read(min(self._avail(), limit))
            searched = self._avail()
            self._fill(self._avail() + 1)


def _split_args(line: bytes) -> tuple[bytes, list[bytes]]:
    body = line[:-1] if line.endswith(b"\n") else line
    prefix, sep, rest = body.partition(b" ")
    if not sep:
        return body, []
    args = rest.split(b" ")
    if len(args) > MAX_ARGS + 1 or not all(_valid_arg(a) for a in args):
        return body, []
    return prefix, args


def parse_header(src: Source) -> Header:
    """從 Source 讀出標頭（讀到 MAC 行的換行為止），失敗時丟 SealError。"""
    start = src.consumed

    def budget() -> int:
        left = MAX_HEADER_BYTES - (src.consumed - start)
        if left <= 0:
            raise header_error("too-large", "age 檔的標頭超過 2 MiB 上限，拒絕處理。")
        return left

    def line() -> bytes:
        got = src.readline(budget())
        if not got.endswith(b"\n"):
            if len(got) and src.consumed - start >= MAX_HEADER_BYTES:
                raise header_error("too-large", "age 檔的標頭超過 2 MiB 上限，拒絕處理。")
            raise header_error("truncated")
        return got

    first = src.readline(len(INTRO))
    if first != INTRO:
        if not first:
            raise fail("unsupported_format", "檔案是空的，不是 age 加密檔。",
                       "確認選對了檔案。", "header:empty")
        if INTRO.startswith(first) or first.startswith(INTRO[:-1]):
            raise header_error("malformed-version-line")
        if first.startswith(VERSION_PREFIX):
            raise fail("unsupported_format", "這是其他版本的 age 檔，這個工具只支援 age v1。",
                       "改用最新版的 age 或 rage 解開。", "header:unsupported-version")
        raise fail("unsupported_format", "這不是 age 加密檔（開頭不是 age 的版本行）。",
                   "確認選對了檔案；舊格式請用對應的模式解密。", "header:not-age")

    stanzas: list[Stanza] = []
    while True:
        budget()
        peek = src.peek(len(FOOTER_PREFIX))
        if len(peek) < len(FOOTER_PREFIX):
            raise header_error("truncated")
        if peek == FOOTER_PREFIX:
            prefix, args = _split_args(line())
            if prefix != FOOTER_PREFIX or len(args) != 1:
                raise header_error("malformed-mac-line")
            try:
                mac = b64_decode_raw(args[0])
            except ValueError:
                raise header_error("malformed-mac") from None
            if len(mac) != MAC_SIZE:
                raise header_error("malformed-mac")
            break
        if len(stanzas) >= MAX_STANZAS:
            raise header_error("too-many-stanzas")
        stanzas.append(_parse_stanza(line))
    if not stanzas:
        raise header_error("no-stanzas")
    return Header(tuple(stanzas), mac)


def _parse_stanza(line) -> Stanza:
    first = line()
    if not first.startswith(STANZA_PREFIX):
        raise header_error("malformed-stanza")
    prefix, args = _split_args(first)
    if prefix != STANZA_PREFIX or not args:
        raise header_error("malformed-stanza")
    body = bytearray()
    while True:
        raw = line()[:-1]
        try:
            chunk = b64_decode_raw(raw)
        except ValueError:
            raise header_error("malformed-stanza-body") from None
        if len(chunk) > BYTES_PER_LINE:
            raise header_error("malformed-stanza-body")
        body += chunk
        if len(chunk) < BYTES_PER_LINE:  # 本體一定以一行短行結束
            break
    names = [a.decode("ascii") for a in args]
    return Stanza(names[0], tuple(names[1:]), bytes(body))
