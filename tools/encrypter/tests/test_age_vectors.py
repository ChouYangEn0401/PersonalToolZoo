"""C2SP CCTV 的 age 官方測試向量（出處與授權見 data/age/PROVENANCE.md）。

* 內附的 128 個向量一定會跑。
* 另外，環境變數 ENCRYPTER_CCTV_AGE_DIR 指到一份 CCTV 資料（可以是 CCTV 的根目錄、
  ``age`` 或 ``age/testdata``）時，也會把那一份完整跑一遍；沒設定就略過並說明。
向量只當資料讀，不執行其中任何東西。後量子（hybrid）向量本工具不支援，略過。
"""

import hashlib
import io
import os
import unittest
import zlib
from pathlib import Path

from _support import Case

from crypto_tool import agefmt
from crypto_tool.agefmt import armor as armor_mod
from crypto_tool.agefmt import stream as stream_mod
from crypto_tool.agefmt.header import Source, parse_header
from crypto_tool.sealed.errors import SealError

DATA = Path(__file__).resolve().parent / "data" / "age"
BUNDLED = DATA / "cctv"
ENV = "ENCRYPTER_CCTV_AGE_DIR"


def parse_vector(raw: bytes) -> dict:
    v = {"identity": [], "passphrase": [], "armored": False, "compressed": False}
    rest = raw
    while True:
        line, sep, rest = rest.partition(b"\n")
        if not sep:
            raise ValueError("invalid vector: no payload")
        if not line:
            break
        key, _, value = line.decode("utf-8").partition(": ")
        if key in ("identity", "passphrase"):
            v[key].append(value)
        elif key == "armored":
            v["armored"] = True
        elif key == "compressed":
            if value != "zlib":
                raise ValueError("unknown compression")
            v["compressed"] = True
        elif key in ("expect", "payload", "file key", "comment"):
            v[key] = value
        else:
            raise ValueError("unknown vector key")
    v["file"] = zlib.decompress(rest) if v["compressed"] else rest
    return v


def is_post_quantum(v: dict) -> bool:
    return any(i.startswith("AGE-SECRET-KEY-PQ-") for i in v["identity"])


def classify(err: SealError) -> str:
    d = err.detail
    if d.startswith("header:"):
        return "header failure"
    if d.startswith("armor:"):
        return "armor failure"
    if d == "hmac":
        return "HMAC failure"
    if d.startswith("payload:"):
        return "payload failure"
    if err.code == "wrong_key":
        return "no match"
    return f"unexpected {err.code}/{d}"


def run_vector(test: unittest.TestCase, name: str, raw: bytes) -> str:
    """跑一個向量；回傳 "ran" 或 "skipped-pq"。"""
    v = parse_vector(raw)
    if is_post_quantum(v):
        return "skipped-pq"
    ids = [agefmt.parse_identity(i) for i in v["identity"]]
    ids += [agefmt.passphrase_identity(p) for p in v["passphrase"]]
    out = io.BytesIO()
    try:
        agefmt.decrypt_stream(io.BytesIO(v["file"]), out, ids, armor=v["armored"])
        got = "success"
    except SealError as exc:
        got = classify(exc)
        if got == "header failure":
            test.assertIn(exc.code, ("corrupt", "unsupported_format"), name)
        elif got in ("armor failure", "HMAC failure", "payload failure"):
            test.assertEqual(exc.code, "corrupt", name)
    test.assertEqual(got, v["expect"], name)
    if "payload" in v and got in ("success", "payload failure"):
        # 失敗的向量也要比對「出錯之前已釋出的明文」
        test.assertEqual(hashlib.sha256(out.getvalue()).hexdigest(), v["payload"], name)
    return "ran"


def load_dir(directory: Path) -> list[tuple[str, bytes]]:
    return [(p.name, p.read_bytes()) for p in sorted(directory.iterdir()) if p.is_file()]


class BundledVectorTests(Case):
    @classmethod
    def setUpClass(cls):
        cls.vectors = load_dir(BUNDLED)

    def test_files_are_intact(self):
        """git 換行轉換會弄壞向量：先比對雜湊清單。"""
        expected = {}
        for line in (DATA / "SHA256SUMS").read_text(encoding="ascii").splitlines():
            digest, name = line.split("  ", 1)
            expected[name] = digest
        got = {name: hashlib.sha256(raw).hexdigest() for name, raw in self.vectors}
        self.assertEqual(set(got), set(expected))
        broken = sorted(n for n in got if got[n] != expected[n])
        self.assertEqual(broken, [], "向量被改過（檢查 tests/data/age/.gitattributes 是否生效）")
        self.assertEqual(len(got), 128)

    def test_decrypt_expectations(self):
        stats = {"ran": 0, "skipped-pq": 0}
        for name, raw in self.vectors:
            with self.subTest(vector=name):
                stats[run_vector(self, name, raw)] += 1
        self.assertEqual(stats, {"ran": 128, "skipped-pq": 0})

    def test_header_reencodes_identically(self):
        """非標頭失敗、非 armor 的向量：解析後重新序列化，位元組完全相同。"""
        count = 0
        for name, raw in self.vectors:
            v = parse_vector(raw)
            if v["armored"] or v["expect"] == "header failure":
                continue
            with self.subTest(vector=name):
                src = Source(io.BytesIO(v["file"]))
                header = parse_header(src)
                rest = src.read(len(v["file"]))
                self.assertEqual(header.marshal() + rest, v["file"])
                count += 1
        self.assertGreater(count, 40)

    def test_stream_reencrypts_identically(self):
        """成功的向量：用向量給的 file key 解開內容，再用同一把金鑰加密，密文完全相同。"""
        count = 0
        for name, raw in self.vectors:
            v = parse_vector(raw)
            if v["armored"] or v["expect"] != "success":
                continue
            with self.subTest(vector=name):
                src = Source(io.BytesIO(v["file"]))
                parse_header(src)
                payload = src.read(len(v["file"]))
                nonce, body = payload[:16], payload[16:]
                key = stream_mod.payload_key(bytes.fromhex(v["file key"]), nonce)
                plain = b"".join(stream_mod.decrypt_payload(io.BytesIO(body).read, key))
                again = io.BytesIO()
                stream_mod.encrypt_payload(io.BytesIO(plain).read, again.write, key)
                self.assertEqual(again.getvalue(), body)
                self.assertEqual(stream_mod.plaintext_size(len(body)), len(plain))
                count += 1
        self.assertGreater(count, 10)

    def test_armor_reencodes_identically(self):
        """armor 正確的向量：解開再編回去，除了 CRLF→LF 與前後空白以外完全相同。"""
        count = 0
        for name, raw in self.vectors:
            v = parse_vector(raw)
            if not v["armored"] or v["expect"] == "armor failure":
                continue
            with self.subTest(vector=name):
                decoded = armor_mod.ArmorReader(io.BytesIO(v["file"])).read()
                out = io.BytesIO()
                w = armor_mod.ArmorWriter(out)
                w.write(decoded)
                w.close()
                expect = v["file"].replace(b"\r\n", b"\n").strip() + b"\n"
                self.assertEqual(out.getvalue(), expect)
                count += 1
        self.assertGreater(count, 5)


class ExternalVectorTests(Case):
    """ENCRYPTER_CCTV_AGE_DIR 指到另外下載的 CCTV 資料時，跑完整一份（含略過的後量子向量統計）。"""

    def test_external_directory(self):
        root = os.environ.get(ENV, "").strip()
        if not root:
            self.skipTest(f"沒有設定 {ENV}，略過外部 CCTV 資料（內附向量已經在 BundledVectorTests 跑過）")
        base = Path(root)
        for candidate in (base / "age" / "testdata", base / "testdata", base):
            if candidate.is_dir() and any(candidate.glob("x25519*")):
                base = candidate
                break
        else:
            self.fail(f"{ENV} 指到的資料夾裡找不到 age 測試向量")
        stats = {"ran": 0, "skipped-pq": 0}
        for name, raw in load_dir(base):
            with self.subTest(vector=name):
                stats[run_vector(self, name, raw)] += 1
        print(f"\n[CCTV external] ran={stats['ran']} skipped(post-quantum)={stats['skipped-pq']}")
        self.assertGreater(stats["ran"], 100)


if __name__ == "__main__":
    unittest.main()
