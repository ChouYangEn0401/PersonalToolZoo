"""Bech32 編碼（BIP-173）。這是「文字編碼」，不是密碼學。

age 規格（c2sp.org/age）用 Bech32 表示金鑰：公鑰 ``age1…``、私鑰 ``AGE-SECRET-KEY-1…``。
規格說明「照 BIP-173，但資料部分沒有長度上限」，所以 ``max_length`` 預設不限制；
測 BIP-173 官方向量時再傳 90。

字串只能全小寫或全大寫；檢查碼一律用小寫的 HRP 計算。
"""

from __future__ import annotations

CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
_CHARSET_INDEX = {c: i for i, c in enumerate(CHARSET)}
_GENERATOR = (0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3)
_MAX_HRP = 83


class Bech32Error(ValueError):
    """Bech32 字串不合法。訊息不含輸入內容（輸入可能是私鑰）。"""


def _polymod(values) -> int:
    chk = 1
    for v in values:
        top = chk >> 25
        chk = ((chk & 0x1FFFFFF) << 5) ^ v
        for i in range(5):
            if (top >> i) & 1:
                chk ^= _GENERATOR[i]
    return chk


def _hrp_expand(hrp: str) -> list[int]:
    h = [ord(c) for c in hrp.lower()]
    return [c >> 5 for c in h] + [0] + [c & 31 for c in h]


def _create_checksum(hrp: str, data: list[int]) -> list[int]:
    mod = _polymod(_hrp_expand(hrp) + data + [0] * 6) ^ 1
    return [(mod >> (5 * (5 - i))) & 31 for i in range(6)]


def convert_bits(data, from_bits: int, to_bits: int, pad: bool) -> list[int]:
    """BIP-173 的 convertbits。pad=False 時拒絕多餘或非零的補位。"""
    acc = 0
    bits = 0
    ret: list[int] = []
    maxv = (1 << to_bits) - 1
    for value in data:
        if value < 0 or value >> from_bits:
            raise Bech32Error("data value out of range")
        acc = (acc << from_bits) | value
        bits += from_bits
        while bits >= to_bits:
            bits -= to_bits
            ret.append((acc >> bits) & maxv)
    if pad:
        if bits:
            ret.append((acc << (to_bits - bits)) & maxv)
    elif bits >= from_bits:
        raise Bech32Error("illegal zero padding")
    elif (acc << (to_bits - bits)) & maxv:
        raise Bech32Error("non-zero padding")
    return ret


def _check_hrp(hrp: str) -> None:
    if not 1 <= len(hrp) <= _MAX_HRP:
        raise Bech32Error("invalid human-readable part length")
    if any(not 33 <= ord(c) <= 126 for c in hrp):
        raise Bech32Error("invalid human-readable part character")


def encode(hrp: str, data: bytes) -> str:
    """把位元組編成 Bech32。HRP 是大寫時，輸出整串大寫（age 私鑰的慣例）。"""
    _check_hrp(hrp)
    if hrp.upper() != hrp and hrp.lower() != hrp:
        raise Bech32Error("mixed-case human-readable part")
    upper = hrp.lower() != hrp
    low = hrp.lower()
    values = convert_bits(data, 8, 5, True)
    out = low + "1" + "".join(CHARSET[v] for v in values + _create_checksum(low, values))
    return out.upper() if upper else out


def decode_raw(s: str, *, max_length: int | None = None) -> tuple[str, list[int]]:
    """解出 (HRP, 5 位元資料值，不含檢查碼)。HRP 保留原本的大小寫。"""
    if not isinstance(s, str):
        raise Bech32Error("not a string")
    if max_length is not None and len(s) > max_length:
        raise Bech32Error("too long")
    if s.lower() != s and s.upper() != s:
        raise Bech32Error("mixed case")
    pos = s.rfind("1")
    if pos < 1 or pos + 7 > len(s):
        raise Bech32Error("separator at invalid position")
    hrp = s[:pos]
    _check_hrp(hrp)
    data: list[int] = []
    for c in s[pos + 1:].lower():
        idx = _CHARSET_INDEX.get(c)
        if idx is None:
            raise Bech32Error("invalid data character")
        data.append(idx)
    if _polymod(_hrp_expand(hrp) + data) != 1:
        raise Bech32Error("invalid checksum")
    return hrp, data[:-6]


def decode(s: str, *, max_length: int | None = None) -> tuple[str, bytes]:
    """解出 (HRP, 位元組)。補位必須是零而且不能多。"""
    hrp, data = decode_raw(s, max_length=max_length)
    return hrp, bytes(convert_bits(data, 5, 8, False))
