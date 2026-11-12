"""age 的內容加密：STREAM（ChaCha20-Poly1305，64 KiB 分塊）。

    payload key = HKDF-SHA-256(ikm=file key, salt=16 位元組 nonce, info="payload")
    每塊的 AEAD nonce = 11 位元組大端序塊編號 || 1 位元組旗標（最後一塊 0x01，其他 0x00）

最後一塊可以比 64 KiB 短，但除非整個內容是空的，否則不能是空塊。
解密照參考實作的順序：讀滿一塊；讀不滿就是最後一塊；讀滿但用「非最後」驗不過時，
再試「最後一塊」（剛好 64 KiB 的最後一塊）；最後一塊之後還有資料就是錯。
記憶體只用到一兩個分塊，不隨檔案大小成長。
"""

from __future__ import annotations

from typing import Callable, Iterator

from ._common import InvalidTag, chacha, hkdf_sha256, payload_error

CHUNK_SIZE = 64 * 1024
TAG_SIZE = 16
ENC_CHUNK_SIZE = CHUNK_SIZE + TAG_SIZE
NONCE_SIZE = 16
_MAX_COUNTER = 1 << 88


def payload_key(file_key: bytes, nonce: bytes) -> bytes:
    return hkdf_sha256(file_key, nonce, b"payload")


def _nonce(counter: int, last: bool) -> bytes:
    if counter >= _MAX_COUNTER:  # 實際上不可能到達
        raise payload_error("counter-overflow")
    return counter.to_bytes(11, "big") + (b"\x01" if last else b"\x00")


def _read_full(read: Callable[[int], bytes], n: int) -> bytes:
    out = bytearray()
    while len(out) < n:
        chunk = read(n - len(out))
        if not chunk:
            break
        out += chunk
    return bytes(out)


def encrypt_payload(read: Callable[[int], bytes], write: Callable[[bytes], object], key: bytes,
                    progress: Callable[[int], None] | None = None) -> int:
    """從 read 讀明文、把密文分塊寫進 write，回傳明文總長度。只保留兩個分塊在記憶體。"""
    aead = chacha(key)
    counter = 0
    total = 0
    cur = _read_full(read, CHUNK_SIZE)
    while True:
        nxt = b""
        if len(cur) == CHUNK_SIZE:
            nxt = _read_full(read, CHUNK_SIZE)
            last = not nxt
        else:
            last = True
        write(aead.encrypt(_nonce(counter, last), cur, None))
        total += len(cur)
        counter += 1
        if progress:
            progress(total)
        if last:
            return total
        cur = nxt


def decrypt_payload(read: Callable[[int], bytes], key: bytes) -> Iterator[bytes]:
    """逐塊產生「已驗證」的明文。出錯時丟 SealError（之前產生的塊都已驗證過）。"""
    aead = chacha(key)
    counter = 0
    while True:
        buf = _read_full(read, ENC_CHUNK_SIZE)
        if not buf:
            raise payload_error("truncated-no-final-chunk")
        last = False
        if len(buf) < ENC_CHUNK_SIZE:
            if counter != 0 and len(buf) == TAG_SIZE:
                raise payload_error("empty-final-chunk")
            last = True
        try:
            plain = aead.decrypt(_nonce(counter, last), buf, None)
        except InvalidTag:
            if last:
                raise payload_error("chunk-authentication-failed") from None
            last = True  # 可能是剛好 64 KiB 的最後一塊
            try:
                plain = aead.decrypt(_nonce(counter, True), buf, None)
            except InvalidTag:
                raise payload_error("chunk-authentication-failed") from None
        counter += 1
        yield plain
        if last:
            if read(1):
                raise payload_error("trailing-data")
            return


def plaintext_size(payload_size: int) -> int | None:
    """由「nonce 之後的密文長度」推算明文長度；長度不合法時回傳 None（不需要金鑰）。"""
    if payload_size <= 0:
        return None
    chunks = (payload_size + ENC_CHUNK_SIZE - 1) // ENC_CHUNK_SIZE
    plain = payload_size - chunks * TAG_SIZE
    if plain < 0:
        return None
    expected = max(1, (plain + CHUNK_SIZE - 1) // CHUNK_SIZE)
    return plain if expected == chunks else None
