"""金鑰來源的解讀，以及檔案／資料夾層級的加解密。金鑰都在測試裡臨時產生。"""

import base64
import io
import os
import tarfile
import unittest

from _support import FAST, Case

from crypto_tool.sealed import keys, ops
from crypto_tool.sealed.container import PAYLOAD_TAR, KeyMaterial, SealWriter


class KeyValueTests(Case):
    def test_value_forms(self):
        raw = os.urandom(32)
        b64 = base64.urlsafe_b64encode(raw).decode()
        std = base64.b64encode(raw).decode()
        for text in (raw.hex(), raw.hex().upper(), "hex:" + raw.hex(), b64, b64.rstrip("="),
                     std, "b64:" + b64, f"  {b64}\n"):
            self.assertEqual(keys.parse_secret_value(text).raw, raw)
        words = keys.parse_secret_value("just some words")
        self.assertIsNone(words.raw)
        self.assertEqual(words.passphrase, "just some words")

    def test_bad_prefixed_values_are_errors_not_passphrases(self):
        self.assertEqual(self.code_of(keys.parse_secret_value, "b64:tooshort"), "bad_key_format")
        self.assertEqual(self.code_of(keys.parse_secret_value, "hex:abcd"), "bad_key_format")
        self.assertEqual(self.code_of(keys.parse_secret_value, "   "), "key_missing")

    def test_typed_passphrase_is_never_treated_as_raw_key(self):
        hexish = "ab" * 32
        material = keys.passphrase_material(hexish + "\r\n")
        self.assertEqual(material.passphrase, hexish)
        self.assertEqual(material.kdf_for_encrypt(), 1)  # scrypt

    def test_key_env(self):
        raw = os.urandom(32)
        self.assertEqual(keys.load_key_env("K", {"K": raw.hex()}).raw, raw)
        self.assertEqual(self.code_of(keys.load_key_env, "K", {}), "key_missing")
        # 有人把金鑰本身塞進 --key-env：拒絕，而且錯誤訊息不能把它印回去
        with self.assertRaises(keys.SealError) as caught:
            keys.load_key_env("not a name! " + raw.hex(), {})
        self.assertEqual(caught.exception.code, "bad_input")
        self.assertNotIn(raw.hex(), str(caught.exception.to_dict()))


class KeyFileTests(Case):
    def test_env_style_key_file(self):
        raw = os.urandom(32)
        path = self.tmp / ".decryption_code.env"
        path.write_text(
            "# comment\n\nOTHER=something else\n"
            f'export CRYPTO_TOOL_KEY="hex:{raw.hex()}"\n', encoding="utf-8")
        self.assertEqual(keys.load_key_file(path).raw, raw)
        self.assertEqual(keys.load_key_file(path, "OTHER").passphrase, "something else")
        self.assertEqual(self.code_of(keys.load_key_file, path, "NOPE"), "key_missing")

    def test_env_file_with_one_name_or_ambiguous(self):
        one = self.tmp / "one.env"
        one.write_text("MY_CODE=open sesame please\n", encoding="utf-8")
        self.assertEqual(keys.load_key_file(one).passphrase, "open sesame please")
        many = self.tmp / "many.env"
        many.write_text("A=one value\nB=two value\n", encoding="utf-8")
        self.assertEqual(self.code_of(keys.load_key_file, many), "bad_key_format")

    def test_raw_and_single_line_key_files(self):
        raw = os.urandom(32)
        binary = self.tmp / "key.bin"
        binary.write_bytes(raw)
        self.assertEqual(keys.load_key_file(binary).raw, raw)
        line = self.tmp / "key.txt"
        line.write_text(base64.b64encode(raw).decode() + "\n", encoding="utf-8")
        self.assertEqual(keys.load_key_file(line).raw, raw)
        bom = self.tmp / "bom.txt"
        bom.write_text(raw.hex(), encoding="utf-8-sig")
        self.assertEqual(keys.load_key_file(bom).raw, raw)

    def test_padded_base64_line_is_not_mistaken_for_an_assignment(self):
        # 全是英數字、結尾補 = 的 base64 看起來像「名稱=」
        raw = bytes.fromhex("00" * 31 + "01")
        text = base64.b64encode(raw).decode()
        self.assertTrue(text.endswith("=") and text[:-1].isalnum())
        path = self.tmp / "k.txt"
        path.write_text(text + "\n", encoding="ascii")
        self.assertEqual(keys.load_key_file(path).raw, raw)

    def test_key_file_problems(self):
        self.assertEqual(self.code_of(keys.load_key_file, self.tmp / "missing.env"), "key_missing")
        empty = self.tmp / "empty.env"
        empty.write_text("\n\n", encoding="utf-8")
        self.assertEqual(self.code_of(keys.load_key_file, empty), "key_missing")
        junk = self.tmp / "junk.bin"
        junk.write_bytes(bytes([0xFF, 0xFE, 0x80]) * 20)
        self.assertEqual(self.code_of(keys.load_key_file, junk), "bad_key_format")
        big = self.tmp / "big.bin"
        big.write_bytes(b"a" * (keys.MAX_KEY_FILE_BYTES + 1))
        self.assertEqual(self.code_of(keys.load_key_file, big), "bad_key_format")

    def test_keygen_roundtrip_and_no_clobber(self):
        path = self.tmp / "new.env"
        info = keys._generate_preview_key_for_tests(path)
        material = keys.load_key_file(path)
        self.assertEqual(len(material.raw), 32)
        self.assertEqual(info["key_id"], keys.key_id(material.raw))
        self.assertNotIn(material.raw.hex(), str(info))
        self.assertNotIn(base64.urlsafe_b64encode(material.raw).decode(), str(info))
        self.assertEqual(self.code_of(keys._generate_preview_key_for_tests, path), "output_exists")
        self.assertEqual(keys.load_key_file(path).raw, material.raw)  # 沒被動到
        keys._generate_preview_key_for_tests(path, force=True)
        self.assertNotEqual(keys.load_key_file(path).raw, material.raw)
        raw_path = self.tmp / "new.key"
        keys._generate_preview_key_for_tests(raw_path, fmt="raw")
        self.assertEqual(raw_path.stat().st_size, 32)


class OpsCase(Case):
    def setUp(self):
        super().setUp()
        self.key = KeyMaterial(raw=os.urandom(32))

    def names(self):
        return sorted(p.name for p in self.tmp.iterdir())


class FileTests(OpsCase):
    def test_roundtrip_with_default_names(self):
        src = self.tmp / "report.pdf"
        data = os.urandom(3000)
        src.write_bytes(data)
        seen = []
        result = ops._encrypt_preview_for_tests(src, None, self.key, chunk_size=1024,
                                  progress=lambda d, t: seen.append((d, t)))
        sealed = self.tmp / "report.pdf.isd2"
        self.assertEqual(result["output"], str(sealed))
        self.assertEqual(result["kdf"], "raw-key")
        self.assertEqual(seen[-1], (3000, 3000))
        self.assertEqual(src.read_bytes(), data)  # 原檔不動
        src.unlink()
        out = ops.decrypt_path(sealed, None, self.key)
        self.assertEqual(out["output"], str(src))
        self.assertEqual(src.read_bytes(), data)
        self.assertEqual([n for n in self.names() if "partial" in n], [])

    def test_existing_target_is_refused_unless_forced(self):
        src = self.tmp / "a.txt"
        src.write_bytes(b"new content")
        dst = self.tmp / "a.txt.isd2"
        dst.write_bytes(b"precious")
        self.assertEqual(self.code_of(ops._encrypt_preview_for_tests, src, dst, self.key), "output_exists")
        self.assertEqual(dst.read_bytes(), b"precious")
        ops._encrypt_preview_for_tests(src, dst, self.key, force=True)
        plain = self.tmp / "out.txt"
        plain.write_bytes(b"precious")
        self.assertEqual(self.code_of(ops.decrypt_path, dst, plain, self.key), "output_exists")
        self.assertEqual(plain.read_bytes(), b"precious")
        ops.decrypt_path(dst, plain, self.key, force=True)
        self.assertEqual(plain.read_bytes(), b"new content")

    def test_failed_decrypt_leaves_nothing_behind(self):
        src = self.tmp / "a.bin"
        src.write_bytes(os.urandom(5000))
        sealed = self.tmp / "a.bin.isd2"
        ops._encrypt_preview_for_tests(src, sealed, self.key, chunk_size=1024)
        blob = bytearray(sealed.read_bytes())
        blob[-5] ^= 1  # 壞在最後一塊：前面幾塊都已經解出來了
        sealed.write_bytes(bytes(blob))
        out = self.tmp / "out.bin"
        before = self.names()
        self.assertEqual(self.code_of(ops.decrypt_path, sealed, out, self.key), "corrupt")
        self.assertEqual(self.names(), before)
        other = KeyMaterial(raw=os.urandom(32))
        self.assertEqual(self.code_of(ops.decrypt_path, sealed, out, other), "wrong_key")
        self.assertFalse(out.exists())

    def test_input_and_output_problems(self):
        key = self.key
        self.assertEqual(self.code_of(ops._encrypt_preview_for_tests, self.tmp / "nope", None, key),
                         "input_missing")
        self.assertEqual(self.code_of(ops.decrypt_path, self.tmp / "nope.isd2", None, key),
                         "input_missing")
        src = self.tmp / "a.txt"
        src.write_bytes(b"x")
        self.assertEqual(self.code_of(ops._encrypt_preview_for_tests, src, src, key), "bad_input")
        self.assertEqual(
            self.code_of(ops._encrypt_preview_for_tests, src, self.tmp / "no_dir" / "o.isd2", key),
            "input_missing")
        self.assertEqual(self.code_of(ops.decrypt_path, src, self.tmp / "o", key),
                         "unsupported_format")
        odd = self.tmp / "sealed.bin"
        ops._encrypt_preview_for_tests(src, odd, key)
        self.assertEqual(self.code_of(ops.decrypt_path, odd, None, key), "bad_input")  # 猜不出輸出檔名

    def test_passphrase_file_roundtrip(self):
        material = keys.passphrase_material("a long enough passphrase")
        src = self.tmp / "a.txt"
        src.write_bytes(b"hello")
        result = ops._encrypt_preview_for_tests(src, None, material, **FAST)
        self.assertEqual(result["kdf"], "scrypt")
        out = self.tmp / "b.txt"
        ops.decrypt_path(self.tmp / "a.txt.isd2", out, material)
        self.assertEqual(out.read_bytes(), b"hello")

    def test_info_needs_no_key_and_recognises_legacy(self):
        src = self.tmp / "a.txt"
        src.write_bytes(b"x" * 10)
        ops._encrypt_preview_for_tests(src, None, self.key, cipher="chacha20-poly1305")
        info = ops.info_path(self.tmp / "a.txt.isd2")
        self.assertEqual((info["format"], info["cipher"], info["kdf"], info["payload"]),
                         ("isd2", "chacha20-poly1305", "raw-key", "file"))
        legacy = self.tmp / "old.isd"
        legacy.write_text(
            'CONTENT="""QUJD"""\nNOTE="""{"algorithm": "AES-256-CBC", "mode": "layered",'
            ' "password_hint": "do not show"}"""', encoding="utf-8")
        old = ops.info_path(legacy)
        self.assertEqual(old["format"], "isd-legacy")
        self.assertEqual(old["legacy_mode"], "layered")
        self.assertNotIn("do not show", str(old))
        self.assertEqual(self.code_of(ops.info_path, src), "unsupported_format")


def make_tree(root):
    (root / "sub" / "deep").mkdir(parents=True)
    (root / "empty").mkdir()
    (root / "a.txt").write_bytes(b"alpha")
    (root / "sub" / "b.bin").write_bytes(os.urandom(4000))
    (root / "sub" / "deep" / "中文 檔名.txt").write_text("內容", encoding="utf-8")
    (root / "zero").write_bytes(b"")


def snapshot(root):
    return {p.relative_to(root).as_posix(): (p.read_bytes() if p.is_file() else None)
            for p in sorted(root.rglob("*"))}


def file_member(name, data=b"evil"):
    info = tarfile.TarInfo(name)
    info.size = len(data)
    return info, io.BytesIO(data)


class FolderTests(OpsCase):
    def setUp(self):
        super().setUp()
        self.src = self.tmp / "project"
        self.src.mkdir()
        make_tree(self.src)

    def test_folder_roundtrip(self):
        key = self.key
        result = ops._encrypt_preview_for_tests(self.src, None, key, chunk_size=512)
        sealed = self.tmp / "project.isd2"
        self.assertEqual((result["payload"], result["files"]), ("folder", 4))
        self.assertEqual(ops.info_path(sealed)["payload"], "folder")
        out = self.tmp / "restored"
        done = ops.decrypt_path(sealed, out, key)
        self.assertEqual(done["files"], 4)
        self.assertEqual(snapshot(out), snapshot(self.src))
        # 預設輸出（去掉 .isd2）就是原本的資料夾，已存在且非空：拒絕，加 force 也一樣
        self.assertEqual(self.code_of(ops.decrypt_path, sealed, None, key), "output_exists")
        self.assertEqual(self.code_of(ops.decrypt_path, sealed, None, key, force=True),
                         "output_exists")
        # 空的資料夾可以直接解進去
        blank = self.tmp / "blank"
        blank.mkdir()
        ops.decrypt_path(sealed, blank, key)
        self.assertEqual(snapshot(blank), snapshot(self.src))

    def test_keep_tar_and_output_inside_source(self):
        key = self.key
        self.assertEqual(self.code_of(ops._encrypt_preview_for_tests, self.src, self.src / "self.isd2", key),
                         "bad_input")
        sealed = self.tmp / "p.isd2"
        ops._encrypt_preview_for_tests(self.src, sealed, key)
        tar_out = self.tmp / "p.tar"
        result = ops.decrypt_path(sealed, tar_out, key, keep_tar=True)
        self.assertEqual(result["payload"], "tar")
        with tarfile.open(tar_out) as tar:
            self.assertIn("sub/deep/中文 檔名.txt", tar.getnames())
            # 封存裡不帶帳號名稱
            self.assertTrue(all(m.uname == "" and m.gname == "" for m in tar.getmembers()))

    def test_truncated_archive_leaves_no_partial_folder(self):
        sealed = self.tmp / "p.isd2"
        ops._encrypt_preview_for_tests(self.src, sealed, self.key, chunk_size=512)
        blob = sealed.read_bytes()
        sealed.write_bytes(blob[: len(blob) - 600])
        before = self.names()
        self.assertEqual(
            self.code_of(ops.decrypt_path, sealed, self.tmp / "restored", self.key), "corrupt")
        self.assertEqual(self.names(), before)

    def _sealed_tar(self, build):
        """用正確的金鑰封一個「內容有問題」的 tar：驗證會過，要靠解開時的檢查擋。"""
        raw = io.BytesIO()
        with tarfile.open(fileobj=raw, mode="w") as tar:
            build(tar)
        path = self.tmp / "bad.isd2"
        with open(path, "wb") as fh:
            writer = SealWriter(fh, self.key, payload=PAYLOAD_TAR)
            writer.write(raw.getvalue())
            writer.close()
        return path

    def test_archive_paths_cannot_escape(self):
        for name in ("../escape.txt", "/abs.txt", "a/../../escape.txt", "C:/abs.txt",
                     "a\\..\\b.txt", "CON", "sub/nul.txt", "com1", "trailing.", "space "):
            with self.subTest(name=name):
                sealed = self._sealed_tar(lambda tar: tar.addfile(*file_member(name)))
                box = self.tmp / "box"
                box.mkdir(exist_ok=True)
                self.assertEqual(
                    self.code_of(ops.decrypt_path, sealed, box / "out", self.key),
                    "unsafe_archive")
                self.assertEqual(list(box.iterdir()), [])
                self.assertFalse((self.tmp / "escape.txt").exists())

    def test_archive_links_are_refused(self):
        def build(tar):
            tar.addfile(*file_member("ok.txt", b"fine"))
            link = tarfile.TarInfo("link")
            link.type = tarfile.SYMTYPE
            link.linkname = "../../somewhere"
            tar.addfile(link)
        sealed = self._sealed_tar(build)
        box = self.tmp / "box"
        box.mkdir()
        self.assertEqual(self.code_of(ops.decrypt_path, sealed, box / "out", self.key),
                         "unsafe_archive")
        self.assertEqual(list(box.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
