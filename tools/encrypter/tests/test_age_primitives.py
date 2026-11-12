"""底層接線：BIP-173（Bech32）公開向量、RFC 7914（scrypt）、RFC 5869（HKDF）、
age 規格裡的範例金鑰、base64 正規形式。"""

import unittest

from _support import Case

from crypto_tool.agefmt import _common, bech32, recipients
from crypto_tool.agefmt.bech32 import Bech32Error

# BIP-173「Test vectors」一節
BIP173_VALID_CHECKSUM = [
    "A12UEL5L",
    "a12uel5l",
    "an83characterlonghumanreadablepartthatcontainsthenumber1andtheexcludedcharactersbio1tt5tgs",
    "abcdef1qpzry9x8gf2tvdw0s3jn54khce6mua7lmqqqxw",
    "11qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqc8247j",
    "split1checkupstagehandshakeupstreamerranterredcaperred2y9e3w",
    "?1ezyfcl",
]
BIP173_INVALID_CHECKSUM = [
    "\x201nwldj5",
    "\x7f1axkwrx",
    "\x801eym55h",
    "an84characterslonghumanreadablepartthatcontainsthenumber1andtheexcludedcharactersbio1569pvx",
    "pzry9x0s0muk",
    "1pzry9x0s0muk",
    "x1b4n0q5v",
    "li1dgmt3",
    "de1lg7wt\xff",
    "A1G7SGD8",
    "10a06t8",
    "1qzzfhee",
]
BIP173_VALID_ADDRESS = [
    ("BC1QW508D6QEJXTDG4Y5R3ZARVARY0C5XW7KV8F3T4", "0014751e76e8199196d454941c45d1b3a323f1433bd6"),
    ("tb1qrp33g0q5c5txsp9arysrx4k6zdkfs4nce4xj0gdcccefvpysxf3q0sl5k7",
     "00201863143c14c5166804bd19203356da136c985678cd4d27a1b8c6329604903262"),
    ("bc1pw508d6qejxtdg4y5r3zarvary0c5xw7kw508d6qejxtdg4y5r3zarvary0c5xw7k7grplx",
     "5128751e76e8199196d454941c45d1b3a323f1433bd6751e76e8199196d454941c45d1b3a323f1433bd6"),
    ("BC1SW50QA3JX3S", "6002751e"),
    ("bc1zw508d6qejxtdg4y5r3zarvaryvg6kdaj", "5210751e76e8199196d454941c45d1b3a323"),
    ("tb1qqqqqp399et2xygdj5xreqhjjvcmzhxw4aywxecjdzew6hylgvsesrxh6hy",
     "0020000000c4a5cad46221b2a187905e5266362b99d5e91c6ce24d165dab93e86433"),
]
# 無效位址裡跟「Bech32 編碼本身」有關的幾個（其餘是 SegWit 層的規則，不在 age 的範圍）
BIP173_INVALID_ENCODING = [
    "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t5",                        # 檢查碼錯
    "tb1qrp33g0q5c5txsp9arysrx4k6zdkfs4nce4xj0gdcccefvpysxf3q0sL5k7",     # 大小寫混用
    "bc1zw508d6qejxtdg4y5r3zarvaryvqyzf3du",                             # 補位超過 4 位元
    "tb1qrp33g0q5c5txsp9arysrx4k6zdkfs4nce4xj0gdcccefvpysxf3pjxtptv",     # 8→5 補位不是零
    "bc1gmk9yu",                                                          # 資料是空的
]


def segwit_script(addr: str) -> str:
    hrp, data = bech32.decode_raw(addr, max_length=90)
    if hrp.lower() not in ("bc", "tb") or not data:
        raise Bech32Error("not a segwit address")
    version = data[0]
    program = bytes(bech32.convert_bits(data[1:], 5, 8, False))
    return (bytes([version + 0x50 if version else 0, len(program)]) + program).hex()


class Bech32Tests(Case):
    def test_valid_checksums(self):
        for s in BIP173_VALID_CHECKSUM:
            with self.subTest(s=s):
                hrp, data = bech32.decode_raw(s, max_length=90)
                # 重新編碼（用 5 位元值）得到同一個字串（大小寫跟原本一致）
                values = data + bech32._create_checksum(hrp.lower(), data)
                again = hrp.lower() + "1" + "".join(bech32.CHARSET[v] for v in values)
                self.assertEqual(again, s.lower())

    def test_invalid_checksums(self):
        for s in BIP173_INVALID_CHECKSUM:
            with self.subTest(s=repr(s)):
                with self.assertRaises(Bech32Error):
                    bech32.decode_raw(s, max_length=90)

    def test_valid_addresses_decode_to_known_programs(self):
        for addr, script in BIP173_VALID_ADDRESS:
            with self.subTest(addr=addr):
                self.assertEqual(segwit_script(addr), script)

    def test_invalid_address_encodings(self):
        for addr in BIP173_INVALID_ENCODING:
            with self.subTest(addr=addr):
                with self.assertRaises(Bech32Error):
                    segwit_script(addr)

    def test_no_length_limit_by_default(self):
        """age 規格：資料部分沒有長度上限。"""
        data = bytes(range(256)) * 2
        s = bech32.encode("age", data)
        self.assertGreater(len(s), 90)
        self.assertEqual(bech32.decode(s), ("age", data))
        with self.assertRaises(Bech32Error):
            bech32.decode(s, max_length=90)

    def test_uppercase_hrp_gives_uppercase_string(self):
        s = bech32.encode("AGE-SECRET-KEY-", b"\x42" * 32)
        self.assertEqual(s, s.upper())
        self.assertEqual(bech32.decode(s), ("AGE-SECRET-KEY-", b"\x42" * 32))


class SpecExampleTests(Case):
    def test_spec_example_key_pair(self):
        """age 規格 X25519 一節的範例私鑰與公鑰是一對。"""
        ident = recipients.parse_identity(
            "AGE-SECRET-KEY-1GFPYYSJZGFPYYSJZGFPYYSJZGFPYYSJZGFPYYSJZGFPYYSJZGFPQ4EGAEX")
        self.assertEqual(ident.public_key, "age1zvkyg2lqzraa2lnjvqej32nkuu0ues2s82hzrye869xeexvn73equnujwj")
        self.assertEqual(ident.secret_key_string(),
                         "AGE-SECRET-KEY-1GFPYYSJZGFPYYSJZGFPYYSJZGFPYYSJZGFPYYSJZGFPYYSJZGFPQ4EGAEX")


class Rfc7914ScryptTests(Case):
    def test_rfc7914_vectors(self):
        from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
        cases = [
            (b"", b"", 16, 1, 1,
             "77d6576238657b203b19ca42c18a0497f16b4844e3074ae8dfdffa3fede21442"
             "fcd0069ded0948f8326a753a0fc81f17e8d3e0fb2e0d3628cf35e20c38d18906"),
            (b"password", b"NaCl", 1024, 8, 16,
             "fdbabe1c9d3472007856e7190d01e9fe7c6ad7cbc8237830e77376634b373162"
             "2eaf30d92e22a3886ff109279d9830dac727afb94a83ee6d8360cbdfa2cc0640"),
            (b"pleaseletmein", b"SodiumChloride", 16384, 8, 1,
             "7023bdcb3afd7348461c06cd81fd38ebfda8fbba904f8e3ea9b543f6545da1f2"
             "d5432955613f0fcf62d49705242a9af9e61e85dc0d651e40dfcf017b45575887"),
        ]
        for pw, salt, n, r, p, hexout in cases:
            with self.subTest(n=n, r=r, p=p):
                self.assertEqual(Scrypt(salt=salt, length=64, n=n, r=r, p=p).derive(pw).hex(), hexout)

    def test_age_wiring_uses_r8_p1(self):
        """age 用 r=8、p=1、dkLen=32：輸出應等於 RFC 第 3 組（N=2^14, r=8, p=1）的前 32 位元組。"""
        out = _common.scrypt_key(b"pleaseletmein", b"SodiumChloride", 14)
        self.assertEqual(out.hex(), "7023bdcb3afd7348461c06cd81fd38ebfda8fbba904f8e3ea9b543f6545da1f2")


class Rfc5869HkdfTests(Case):
    def test_rfc5869_sha256_vectors(self):
        cases = [
            ("0b" * 22, "000102030405060708090a0b0c", "f0f1f2f3f4f5f6f7f8f9", 42,
             "3cb25f25faacd57a90434f64d0362f2a2d2d0a90cf1a5a4c5db02d56ecc4c5bf34007208d5b887185865"),
            (bytes(range(0x00, 0x50)).hex(), bytes(range(0x60, 0xB0)).hex(), bytes(range(0xB0, 0x100)).hex(), 82,
             "b11e398dc80327a1c8e7f78c596a49344f012eda2d4efad8a050cc4c19afa97c"
             "59045a99cac7827271cb41c65e590e09da3275600c2f09b8367793a9aca3db71"
             "cc30c58179ec3e87c14c01d5c1f3434f1d87"),
            ("0b" * 22, "", "", 42,
             "8da4e775a563c18f715f802a063c5a31b8a11f5c5ee1879ec3454e5f3c738d2d9d201395faa4b61a96c8"),
        ]
        for ikm, salt, info, length, okm in cases:
            with self.subTest(length=length, salt=len(salt)):
                got = _common.hkdf_sha256(bytes.fromhex(ikm), bytes.fromhex(salt), bytes.fromhex(info), length)
                self.assertEqual(got.hex(), okm)


class Base64Tests(Case):
    def test_canonical_unpadded(self):
        self.assertEqual(_common.b64_decode_raw(b"AQID"), b"\x01\x02\x03")
        self.assertEqual(_common.b64_decode_raw(b"AQ"), b"\x01")
        self.assertEqual(_common.b64_decode_raw(b""), b"")
        for bad in (b"AQ==", b"AR", b"A", b"AQ\r", b"AQ\n", b"A Q", b"AQ-_"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    _common.b64_decode_raw(bad)

    def test_canonical_padded(self):
        self.assertEqual(_common.b64_decode_padded(b"AQ=="), b"\x01")
        for bad in (b"AQ", b"AR==", b"AQ=", b"A===", b"AQ==AQ=="):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    _common.b64_decode_padded(bad)


if __name__ == "__main__":
    unittest.main()
