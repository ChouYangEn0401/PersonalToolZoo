"""PGP 模式的操作：產生金鑰、加密、解密、看資訊。全部透過系統上的 gpg，產生標準 OpenPGP 檔案。

原則（跟 sealed/ops.py 一致）：
* 輸出先寫到目標旁邊的暫存檔，gpg 成功**而且**完整性檢查通過才改名成目標；
  失敗一律刪掉暫存檔，不留半個檔案、不留沒通過驗證的明文。
* 目標已存在就拒絕，除非呼叫端明確要求覆蓋。
* 互通性：加密一律 ``--compliance=openpgp``（RFC 4880：SEIPD v1＋MDC），產生的金鑰不宣告 AEAD；
  寫完再檢查一次封包種類（理由見 docs/pgp-mode.md）。
"""

from __future__ import annotations

import os
import re
import secrets
from pathlib import Path
from typing import Iterable

from . import _gpg
from ._gpg import GpgInfo, GpgResult, GpgSession, check_passphrase, find_gpg, timeout_for

try:
    from ..sealed.errors import SealError
except ImportError:  # pragma: no cover
    from sealed.errors import SealError

PathLike = str | os.PathLike

# 產生金鑰的種類 → (主金鑰演算法, 加密子金鑰演算法)
KEY_TYPES = {
    "ed25519": ("ed25519", "cv25519"),
    "rsa3072": ("rsa3072", "rsa3072"),
    "rsa4096": ("rsa4096", "rsa4096"),
}
UNPROTECTED_COMMENT = "WARNING: this secret key is NOT protected by a passphrase"

_PUBKEY_ALGOS = {1: "RSA", 2: "RSA", 3: "RSA", 16: "ElGamal", 18: "ECDH", 25: "X25519", 26: "X448"}
_ENCRYPT_CMD = ["--compliance=openpgp", "--personal-cipher-preferences", "AES256 AES192 AES",
                "--no-encrypt-to"]
_GPG_ERR_BAD_PASSPHRASE = 11
_GPG_ERR_NO_PASSPHRASE = 177


# ---------------------------------------------------------------- 辨識

_ARMOR_RE = re.compile(rb"^-----BEGIN PGP ([A-Z ,/0-9]+)-----")
_ARMOR_KINDS = (
    (b"MESSAGE", "message"),
    (b"PUBLIC KEY BLOCK", "public_key"),
    (b"PRIVATE KEY BLOCK", "secret_key"),
    (b"SIGNED MESSAGE", "signed_text"),
    (b"SIGNATURE", "signature"),
)
# 第一個封包的 tag → (種類, 可接受的版本位元組；None 表示這種封包沒有版本位元組)
_FIRST_PACKET = {
    1: ("message", {3, 6}),          # PKESK（公鑰加密的工作階段金鑰）
    3: ("message", {4, 5, 6}),       # SKESK（密語加密的工作階段金鑰）
    18: ("message", {1, 2}),         # SEIPD
    20: ("message", {1}),            # LibrePGP 的 OCB 資料封包
    6: ("public_key", {2, 3, 4, 5, 6}),
    5: ("secret_key", {2, 3, 4, 5, 6}),
    2: ("signature", {2, 3, 4, 5, 6}),
    4: ("message", {3, 6}),          # 一次性簽章（已簽章但沒加密的訊息）
    8: ("message", {0, 1, 2, 3}),    # 壓縮封包（沒加密）：版本位元組的位置是壓縮演算法
}
_PARTIAL_OK = {8, 9, 11, 18, 20}     # 允許「部分長度」的資料封包


def pgp_kind(head: bytes) -> str | None:
    """看檔案開頭（建議至少 64 位元組）判斷是哪一種 OpenPGP 資料。

    回傳 ``"message"``（加密或簽章訊息）、``"public_key"``、``"secret_key"``、``"signature"``、
    ``"signed_text"``；不像 OpenPGP 就回傳 None。二進位封包與 ASCII armor 都認得。
    """
    if not head:
        return None
    text = head.lstrip(b"\xef\xbb\xbf").lstrip(b" \t\r\n")
    match = _ARMOR_RE.match(text)
    if match:
        label = match.group(1)
        for prefix, kind in _ARMOR_KINDS:
            if label.startswith(prefix):
                return kind
        return None
    return _binary_kind(head)


def _binary_kind(head: bytes) -> str | None:
    ctb = head[0]
    if not ctb & 0x80:
        return None
    pos = 1
    if ctb & 0x40:                       # 新格式
        tag = ctb & 0x3F
        if len(head) < 2:
            return None
        first = head[1]
        if first < 192:
            length, pos = first, 2
        elif first < 224:
            if len(head) < 3:
                return None
            length, pos = ((first - 192) << 8) + head[2] + 192, 3
        elif first == 255:
            if len(head) < 6:
                return None
            length, pos = int.from_bytes(head[2:6], "big"), 6
        else:                            # 部分長度
            if tag not in _PARTIAL_OK:
                return None
            length, pos = 1 << (first & 0x1F), 2
    else:                                # 舊格式
        tag = (ctb >> 2) & 0x0F
        ltype = ctb & 0x03
        size = {0: 1, 1: 2, 2: 4}.get(ltype)
        if size is None:                 # 不定長度：只有資料封包會用
            if tag not in _PARTIAL_OK:
                return None
            length = None
        else:
            if len(head) < 1 + size:
                return None
            length = int.from_bytes(head[1:1 + size], "big")
            pos = 1 + size
    spec = _FIRST_PACKET.get(tag)
    if spec is None or (length is not None and length < 2) or len(head) <= pos:
        return None
    kind, versions = spec
    return kind if head[pos] in versions else None


def is_pgp(head_bytes: bytes) -> bool:
    """檔案開頭像不像 OpenPGP 資料（加密訊息、金鑰、簽章；二進位或 armor）。"""
    return pgp_kind(head_bytes) is not None


def _read_head(path: Path, size: int = 4096) -> bytes:
    try:
        with open(path, "rb") as fh:
            return fh.read(size)
    except OSError as exc:
        raise SealError("io_error", "讀不到檔案。", detail=type(exc).__name__) from None


# ---------------------------------------------------------------- 封包清單

def _parse_packets(listing: str) -> dict:
    recipients: list[dict] = []
    passphrase_packets = 0
    data_packet = None
    top_tags: list[int] = []
    current = None
    for raw in listing.splitlines():
        line = raw.strip()
        m = re.match(r"# off=\d+ ctb=[0-9a-f]+ tag=(\d+)", line)
        if m:
            current = int(m.group(1))
            top_tags.append(current)
            continue
        if line.startswith(":pubkey enc packet:"):
            kid = re.search(r"keyid ([0-9A-Fa-f]{16})", line)
            algo = re.search(r"algo (\d+)", line)
            algo_n = int(algo.group(1)) if algo else None
            recipients.append({
                "key_id": kid.group(1).upper() if kid else None,
                "algo": algo_n,
                "algo_name": _PUBKEY_ALGOS.get(algo_n, "unknown"),
            })
        elif line.startswith(":symkey enc packet:"):
            passphrase_packets += 1
        elif line.startswith(":encrypted data packet:"):
            data_packet = "sed" if current == 9 else "seipd_v1"
        elif line.startswith(":aead encrypted packet:"):
            data_packet = "aead_ocb" if "aead=2" in line else "aead"
        elif line.startswith("mdc_method:") and data_packet == "seipd_v1":
            if line.split(":", 1)[1].strip() == "0":
                data_packet = "sed"
    if data_packet is None:
        if 9 in top_tags:
            data_packet = "sed"
        elif 18 in top_tags:
            data_packet = "seipd_v1"
        elif 20 in top_tags:
            data_packet = "aead"
    hidden = sum(1 for r in recipients if r["key_id"] == "0" * 16)
    return {
        "recipients": recipients,
        "recipient_count": len(recipients),
        "hidden_recipients": hidden,
        "passphrase_packets": passphrase_packets,
        "has_passphrase": passphrase_packets > 0,
        "data_packet": data_packet,
        "encrypted": data_packet is not None,
        "integrity_protected": data_packet in ("seipd_v1", "aead", "aead_ocb"),
        # 只有 SEIPD v1（RFC 4880＋MDC）是幾乎所有 OpenPGP 實作都解得開的
        "interoperable": data_packet == "seipd_v1",
    }


def _list_packets(session: GpgSession, path: Path) -> dict:
    res = session.run(["--list-only", "--list-packets", str(path)], timeout=timeout_for(path))
    info = _parse_packets(res.output)
    if not info["encrypted"] and res.returncode != 0:
        raise SealError("corrupt", "讀不懂這個 OpenPGP 檔案（可能損壞或被截斷）。",
                        detail=res.summary())
    return info


def inspect(path: PathLike) -> dict:
    """不需要金鑰就能看的資訊：armor、收件人 key ID、有沒有密語封包、資料封包種類。"""
    src = Path(os.path.abspath(path))   # 理由同 _as_paths
    if not src.is_file():
        raise SealError("input_missing", "找不到檔案。")
    head = _read_head(src)
    kind = pgp_kind(head)
    if kind is None:
        raise SealError("unsupported_format", "這不是 OpenPGP 檔案。",
                        action="確認選對檔案；其他格式請用對應的模式查看。")
    data = {
        "action": "inspect", "format": "openpgp", "input": str(src),
        "size": src.stat().st_size, "kind": kind,
        "armor": head.lstrip(b"\xef\xbb\xbf \t\r\n").startswith(b"-----BEGIN PGP "),
    }
    if kind != "message":
        data.update({"encrypted": False, "recipients": [], "recipient_count": 0,
                     "hidden_recipients": 0, "passphrase_packets": 0, "has_passphrase": False,
                     "data_packet": None, "integrity_protected": False, "interoperable": False})
        return data
    with GpgSession() as session:
        data.update(_list_packets(session, src))
    return data


# ---------------------------------------------------------------- 檔案輸出的共用規則

def _temp_beside(dst: Path) -> Path:
    return dst.with_name(f".{dst.name}.partial-{secrets.token_hex(4)}")


def _remove(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


def _fsync(path: Path) -> None:
    try:
        with open(path, "rb+") as fh:
            os.fsync(fh.fileno())
    except OSError:
        pass


def _check_target(dst: Path, overwrite: bool, what: str = "輸出檔") -> None:
    if not dst.parent.is_dir():
        raise SealError("input_missing", f"{what}所在的資料夾不存在。",
                        action="先建立資料夾，或換一個輸出位置。")
    if dst.is_dir():
        raise SealError("output_exists", f"{what}的位置是一個已存在的資料夾。",
                        action="指定一個檔名。")
    if dst.exists() and not overwrite:
        raise SealError("output_exists", f"{what}已經存在，沒有覆蓋。",
                        action="換一個輸出位置，或確定要覆蓋時明確要求覆蓋。")


def _commit(tmp: Path, dst: Path, overwrite: bool) -> None:
    """暫存檔改名成目標。沒有要求覆蓋時，目標在這期間冒出來也不會被蓋掉。"""
    _fsync(tmp)
    try:
        if overwrite:
            os.replace(tmp, dst)
        elif os.name == "nt":
            os.rename(tmp, dst)          # Windows：目標存在會失敗
        else:
            try:
                os.link(tmp, dst)        # 目標存在會失敗
                tmp.unlink()
            except FileExistsError:
                raise
            except OSError:
                if dst.exists():
                    raise FileExistsError(str(dst)) from None
                os.rename(tmp, dst)
    except FileExistsError:
        _remove(tmp)
        raise SealError("output_exists", "輸出檔已經存在，沒有覆蓋。",
                        action="換一個輸出位置。") from None
    except OSError as exc:
        _remove(tmp)
        raise SealError("io_error", "寫入輸出檔失敗（權限不足、磁碟滿了，或檔案正被別的程式使用）。",
                        detail=type(exc).__name__) from None


def _as_paths(value, what: str) -> list[Path]:
    if value is None:
        return []
    if isinstance(value, (str, os.PathLike)):
        value = [value]
    # gpg 在暫時 home 裡執行（cwd 是那個資料夾），相對路徑會被當成相對於它，所以一律轉成絕對路徑
    paths = [Path(os.path.abspath(v)) for v in value]
    for p in paths:
        if not p.is_file():
            raise SealError("key_missing", f"找不到{what}檔：{p.name}",
                            action="確認金鑰檔的位置。")
    return paths


def _check_src_dst(src: PathLike, dst: PathLike, overwrite: bool) -> tuple[Path, Path]:
    src_p, dst_p = Path(os.path.abspath(src)), Path(os.path.abspath(dst))   # 理由同 _as_paths
    if not src_p.exists():
        raise SealError("input_missing", "找不到輸入檔。")
    if not src_p.is_file():
        raise SealError("bad_input", "PGP 模式一次只處理一個一般檔案（資料夾請先打包）。")
    if src_p.resolve() == dst_p.resolve():
        raise SealError("bad_input", "輸出位置不能跟輸入是同一個。")
    _check_target(dst_p, overwrite)
    return src_p.resolve(), dst_p.resolve()


# ---------------------------------------------------------------- 匯入金鑰

def _import_keys(session: GpgSession, files: list[Path], *, secret: bool) -> list[str]:
    """把金鑰檔匯入暫時 home，回傳主金鑰指紋（去重、保持順序）。"""
    found: list[str] = []
    what = "私鑰" if secret else "公鑰"
    for path in files:
        res = session.run(["--import", str(path)])
        fprs, has_secret = [], False
        for args in res.args_of("IMPORT_OK"):
            if len(args) >= 2:
                fprs.append(args[1].upper())
                try:
                    has_secret = has_secret or bool(int(args[0]) & 16)
                except ValueError:
                    pass
        if not fprs:
            raise SealError("bad_key_format", f"{path.name} 不是可用的 OpenPGP {what}檔。",
                            action=f"確認選的是 ASCII armor 或二進位的 OpenPGP {what}匯出檔。",
                            detail=res.summary())
        if secret and not has_secret:
            raise SealError("bad_key_format", f"{path.name} 只有公鑰，沒有私鑰，不能用來解密。",
                            action="選匯出的私鑰檔（-----BEGIN PGP PRIVATE KEY BLOCK-----）。")
        for fpr in fprs:
            if fpr not in found:
                found.append(fpr)
    return found


# ---------------------------------------------------------------- 產生金鑰

_EMAIL_RE = re.compile(r"^[^@\s<>()]+@[^@\s<>()]+\.[^@\s<>()]+$")


def _user_id(name: str, email: str | None) -> str:
    name = (name or "").strip()
    if not name or len(name) > 128:
        raise SealError("bad_input", "金鑰名稱不能是空的，也不能超過 128 個字。")
    if any(ch in name for ch in "<>\r\n\x00") or name.startswith("#"):
        raise SealError("bad_input", "金鑰名稱不能包含 < > 或換行。")
    if email is None or not email.strip():
        return name
    email = email.strip()
    if not _EMAIL_RE.match(email):
        raise SealError("bad_input", "電子郵件格式不對。", action="例如 name@example.com；不需要可以留空。")
    return f"{name} <{email}>"


def _is_protected(listing: str) -> bool:
    """私鑰匯出檔的封包清單裡，每個私鑰封包都有 S2K 保護才算有密語。"""
    blocks = re.split(r"\n(?=# off=)", listing)
    secret_blocks = [b for b in blocks if ":secret key packet:" in b or ":secret sub key packet:" in b]
    return bool(secret_blocks) and all("S2K" in b or "protected" in b for b in secret_blocks)


def generate_keypair(
    name: str,
    email: str | None = None,
    *,
    out_public: PathLike,
    out_secret: PathLike,
    passphrase: str | None = None,
    overwrite: bool = False,
    key_type: str = "ed25519",
    out_revocation: PathLike | None = None,
) -> dict:
    """產生一組 OpenPGP 金鑰對，公鑰／私鑰各匯出成 ASCII armor 檔。

    回傳 ``{"fingerprint", "uid", "public_key", "secret_key", "protected", ...}``。
    沒有密語時 ``protected`` 是 False、帶 ``warning``，私鑰檔也會有一行 ``Comment:`` 警告。
    檔案已存在就拒絕（``overwrite=True`` 才覆蓋）。產生後會在另一個暫時 home 匯入私鑰、
    實際加解密一次做自我檢查，通過才寫出檔案。
    """
    uid = _user_id(name, email)
    if key_type not in KEY_TYPES:
        raise SealError("bad_input", f"不支援的金鑰種類：{key_type}",
                        action="可用：" + "、".join(KEY_TYPES))
    if passphrase == "":
        passphrase = None
    if passphrase is not None:
        check_passphrase(passphrase, "私鑰密語")
    targets = [Path(out_public).resolve(), Path(out_secret).resolve()]
    if out_revocation is not None:
        targets.append(Path(out_revocation).resolve())
    if len({str(t).lower() if os.name == "nt" else str(t) for t in targets}) != len(targets):
        raise SealError("bad_input", "公鑰、私鑰（與撤銷憑證）要存成不同的檔案。")
    for t in targets:
        _check_target(t, overwrite, "金鑰檔")

    primary, sub = KEY_TYPES[key_type]
    pw = passphrase or ""
    info = find_gpg()
    temps = [_temp_beside(t) for t in targets]
    try:
        with GpgSession(info) as s:
            res = s.run(["--compliance=openpgp", "--quick-generate-key", uid, primary,
                         "cert,sign", "never"], passphrase=pw)
            created = [a[1] for a in res.args_of("KEY_CREATED") if len(a) >= 2]
            if res.returncode != 0 or not created:
                raise SealError("io_error", "gpg 產生金鑰失敗。", detail=res.summary((pw,)))
            fpr = created[0].upper()
            res = s.run(["--compliance=openpgp", "--quick-add-key", fpr, sub, "encr", "never"],
                        passphrase=pw)
            if res.returncode != 0 or not res.has("KEY_CREATED"):
                raise SealError("io_error", "gpg 產生加密用子金鑰失敗。", detail=res.summary((pw,)))
            res = s.run(["--armor", "-o", str(temps[0]), "--export", fpr])
            if res.returncode != 0 or not temps[0].is_file():
                raise SealError("io_error", "匯出公鑰失敗。", detail=res.summary((pw,)))
            export = ["--armor"]
            if passphrase is None:
                export += ["--comment", UNPROTECTED_COMMENT]
            res = s.run(export + ["-o", str(temps[1]), "--export-secret-keys", fpr], passphrase=pw)
            if res.returncode != 0 or not temps[1].is_file():
                raise SealError("io_error", "匯出私鑰失敗。", detail=res.summary((pw,)))
            if out_revocation is not None:
                rev = s.folder / "openpgp-revocs.d" / f"{fpr}.rev"
                try:
                    temps[2].write_bytes(rev.read_bytes())
                except OSError as exc:
                    raise SealError("io_error", "gpg 沒有產生撤銷憑證。",
                                    detail=type(exc).__name__) from None
        protected = _self_check(info, temps[0], temps[1], fpr, pw)
        if protected != (passphrase is not None):
            raise SealError("io_error", "產生的私鑰保護狀態跟要求的不一樣，沒有寫出檔案。")
        for i, (tmp, dst) in enumerate(zip(temps, targets)):
            try:
                _commit(tmp, dst, overwrite)
            except SealError:
                for done in targets[:i]:   # 已經放好的也收回，不留半組金鑰
                    _remove(done)
                raise
    finally:
        for tmp in temps:
            _remove(tmp)

    result = {
        "action": "keygen", "format": "openpgp", "fingerprint": fpr, "uid": uid,
        "key_type": key_type, "public_key": str(targets[0]), "secret_key": str(targets[1]),
        "protected": protected, "gpg": info.version,
    }
    if out_revocation is not None:
        result["revocation"] = str(targets[2])
    if not protected:
        result["warning"] = "私鑰沒有密語保護：拿到私鑰檔的人就能解密，請妥善保管。"
    return result


def _self_check(info: GpgInfo, public: Path, secret: Path, fpr: str, pw: str) -> bool:
    """在全新的暫時 home 匯入私鑰，加密一小段資料再解開。回傳私鑰是否有密語保護。"""
    with GpgSession(info) as s:
        listing = s.run(["--list-packets", str(secret)]).output
        protected = _is_protected(listing)
        pub_listing = s.run(["--list-packets", str(public)]).output
        if "pref-aead-algos" in pub_listing or re.search(r"features: 0[2-9a-fA-F]", pub_listing):
            raise SealError("io_error", "產生的金鑰宣告了 AEAD，沒有寫出檔案。")
    s, fprs, states = _session_with_keys(info, [secret], pw)
    s.close()
    if fpr not in fprs:
        raise SealError("io_error", "產生的私鑰檔自我檢查失敗（匯入後找不到金鑰）。")
    if states[fpr] != "ok":
        raise SealError("io_error", "產生的私鑰檔自我檢查失敗（用匯出的私鑰解不開），沒有寫出檔案。",
                        action="再試一次；一直失敗請回報 gpg 版本。", detail=states[fpr])
    return protected


def _session_with_keys(info: GpgInfo, keys: list[Path], pw: str) -> tuple[GpgSession, list[str], dict[str, str]]:
    """開一個暫時 home、匯入私鑰、把每把私鑰實際用一次（_warm_up）。回傳**還開著**的 session，呼叫端負責 close()。

    為什麼要換 home 重來：GnuPG 2.4.9（Git for Windows）把匯入的私鑰轉成 agent 自己的格式時，
    會不會「Bad secret key」跟 home 路徑的長度、金鑰、同時匯入哪幾把有關，同一個 home 裡重試沒用
    （見 _gpg.py 開頭 HOME_LEN 的說明）。所以有私鑰轉換失敗時，換 HOME_LEN_CHOICES 裡下一個長度的 home 再試；
    全部試完還是失敗就回傳最後一次的結果（之後的解密會照實回報 Bad secret key）。
    """
    choices = _gpg.HOME_LEN_CHOICES
    for i, length in enumerate(choices):
        s = GpgSession(info, home_len=length).__enter__()
        try:
            fprs = _import_keys(s, keys, secret=True)
            states = _warm_up(s, fprs, pw)
        except BaseException:
            s.close()
            raise
        if "failed" not in states.values() or i == len(choices) - 1:
            return s, fprs, states
        s.close()
    raise AssertionError("unreachable")


_WARM_ATTEMPTS = 4         # gpg 偶發的 Bad secret key（見下方說明）在同一個 home 裡最多重試幾次；之後換 home
_WARM_BAD_PASS = 3         # 連續幾次「密語不對」才相信真的是密語不對
_GPG_ERR_BAD_SECKEY = 7


def _warm_up(session: GpgSession, fprs: list[str], pw: str) -> dict[str, str]:
    """匯入私鑰後，用一小段測試資料把每把私鑰實際解一次，直到成功。

    為什麼要這樣：GnuPG 匯入 OpenPGP 私鑰時，gpg-agent 先存成「openpgp-native」格式，
    第一次使用時才轉換。實測 Git for Windows 附的 GnuPG 2.4.9（libgcrypt 1.12）對
    Curve25519 私鑰的這個轉換**會隨機失敗**（Bad secret key；有密語的私鑰偶爾報 Bad passphrase），
    同一把私鑰重試幾次就會成功，成功後 agent 會記住、之後都正常。所以先用測試資料把轉換做完，
    真正的檔案只要解一次（大檔不必重讀）。

    回傳 {指紋: "ok" | "bad_passphrase" | "no_encryption_key" | "failed"}。
    """
    probe = secrets.token_bytes(32)
    plain = session.folder / "warm.bin"
    plain.write_bytes(probe)
    states: dict[str, str] = {}
    for i, fpr in enumerate(fprs):
        enc = session.folder / f"warm-{i}.gpg"
        res = session.run(_ENCRYPT_CMD + ["-o", str(enc), "--encrypt", "--recipient", fpr, str(plain)])
        if res.returncode != 0 or not enc.is_file():
            states[fpr] = "no_encryption_key"
            continue
        bad_pass = 0
        states[fpr] = "failed"
        for n in range(_WARM_ATTEMPTS):
            out = session.folder / f"warm-{i}-{n}.out"
            res = session.run(["--skip-verify", "-o", str(out), "--decrypt", str(enc)], passphrase=pw)
            if res.returncode == 0 and res.has("DECRYPTION_OKAY") and out.is_file() \
                    and out.read_bytes() == probe:
                states[fpr] = "ok"
                break
            codes = {code for loc, code in res.error_codes() if loc.startswith("pkdecrypt")}
            if codes & {_GPG_ERR_BAD_PASSPHRASE, _GPG_ERR_NO_PASSPHRASE}:
                bad_pass += 1
                if bad_pass >= _WARM_BAD_PASS:
                    states[fpr] = "bad_passphrase"
                    break
            elif _GPG_ERR_BAD_SECKEY not in codes:
                break
    return states


# ---------------------------------------------------------------- 加密

def encrypt_file(
    src: PathLike,
    dst: PathLike,
    *,
    recipient_key_files: Iterable[PathLike] = (),
    passphrase: str | None = None,
    armor: bool = False,
    overwrite: bool = False,
) -> dict:
    """把一個檔案加密成標準 OpenPGP（``.gpg``；``armor=True`` 時是文字的 ``.asc``）。

    收件人（公鑰檔，可多個）與密語至少要有一個，兩者可以並存：同一份密文，
    任何一把對應的私鑰、或密語，都能解開（萬用鎖）。
    """
    src_p, dst_p = _check_src_dst(src, dst, overwrite)
    keys = _as_paths(recipient_key_files, "公鑰")
    if passphrase is not None:
        check_passphrase(passphrase)
    if not keys and passphrase is None:
        raise SealError("bad_input", "至少要指定一把收件人公鑰或一個密語。",
                        action="加上收件人的公鑰檔，或設定密語。")
    info = find_gpg()
    tmp = _temp_beside(dst_p)
    hide = (passphrase or "",)
    try:
        with GpgSession(info) as s:
            fprs = _import_keys(s, keys, secret=False) if keys else []
            args = list(_ENCRYPT_CMD)
            if armor:
                args.append("--armor")
            args += ["-o", str(tmp)]
            if fprs:
                args.append("--encrypt")
                for fpr in fprs:
                    args += ["--recipient", fpr]
            if passphrase is not None:
                args.append("--symmetric")
            args.append(str(src_p))
            res = s.run(args, passphrase=passphrase, timeout=timeout_for(src_p))
            if res.returncode != 0 or not res.has("END_ENCRYPTION") or not tmp.is_file():
                _raise_encrypt_error(res, hide)
            packets = _list_packets(s, tmp)
        if packets["data_packet"] != "seipd_v1":
            raise SealError("unsupported_format",
                            "gpg 產生的資料封包不是 SEIPD v1，其他 OpenPGP 程式可能解不開，已放棄這次輸出。",
                            action="檢查 gpg 的全域設定（例如 force-aead），或換一個 gpg。",
                            detail=str(packets["data_packet"]))
        _commit(tmp, dst_p, overwrite)
    finally:
        _remove(tmp)
    return {
        "action": "encrypt", "format": "openpgp", "input": str(src_p), "output": str(dst_p),
        "armor": bool(armor), "recipients": fprs, "recipient_count": len(fprs),
        "passphrase": passphrase is not None, "data_packet": packets["data_packet"],
        "bytes_in": src_p.stat().st_size, "bytes_out": dst_p.stat().st_size, "gpg": info.version,
    }


_INV_RECP = {
    "1": "找不到", "2": "不明確", "3": "這把金鑰不能用來加密（沒有加密用的子金鑰）",
    "4": "已被撤銷", "5": "已過期", "10": "不被信任",
}


def _raise_encrypt_error(res: GpgResult, hide: tuple[str, ...]) -> None:
    bad = res.args_of("INV_RECP")
    if bad:
        reason = _INV_RECP.get(bad[0][0] if bad[0] else "", "不能使用")
        raise SealError("bad_key_format", f"收件人公鑰不能用：{reason}。",
                        action="換一把有效的公鑰（未過期、未撤銷、有加密用子金鑰）。",
                        detail=res.summary(hide))
    raise SealError("io_error", "gpg 加密失敗。", action="確認輸入檔可以讀、輸出位置可以寫。",
                    detail=res.summary(hide))


# ---------------------------------------------------------------- 解密

class _Failure(Exception):
    def __init__(self, code: str, reason: str, action: str = "", detail: str = ""):
        super().__init__(reason)
        self.code, self.reason, self.action, self.detail = code, reason, action, detail


def _check_decrypt(res: GpgResult, mode: str, hide: tuple[str, ...]) -> None:
    """依 gpg 的狀態行判斷解密是否真的成功；不成功就丟 _Failure（附分類）。"""
    detail = res.summary(hide)
    infos = res.args_of("DECRYPTION_INFO")
    aead = any(len(a) >= 3 and a[2] not in ("", "0") for a in infos)
    no_mdc = any(a and a[0] == "0" and not (len(a) >= 3 and a[2] not in ("", "0")) for a in infos)
    if (res.returncode == 0 and res.has("DECRYPTION_OKAY") and (res.has("GOODMDC") or aead)
            and not res.has("BADMDC") and not res.has("DECRYPTION_FAILED")):
        return
    if res.has("BADMDC"):
        raise _Failure("corrupt", "檔案被改過或損壞（完整性檢查沒通過），沒有輸出任何內容。",
                       "不要使用這個檔案；向提供者要一份新的。", detail)
    if no_mdc:
        raise _Failure("unsupported_format", "這是沒有完整性保護的舊式加密檔，不安全，沒有解開。",
                       "請對方用新版 OpenPGP 程式重新加密。", detail)
    if res.has("NODATA") and not res.has("BEGIN_DECRYPTION"):
        raise _Failure("corrupt", "檔案內容不完整或不是有效的 OpenPGP 加密資料。", "", detail)
    if mode == "key":
        if not res.has("DECRYPTION_KEY"):
            if any(code == _GPG_ERR_BAD_SECKEY for loc, code in res.error_codes()
                   if loc.startswith("pkdecrypt")):
                raise _Failure("wrong_key", "gpg 無法使用這把私鑰（Bad secret key）。",
                               "再試一次；一直失敗時確認私鑰檔沒有損壞，或改用 Gpg4win 的 gpg"
                               "（設定環境變數 ENCRYPTER_GPG）。", detail)
            if _bad_passphrase(res, "pkdecrypt") or res.has("NEED_PASSPHRASE"):
                raise _Failure("wrong_key", "私鑰的密語不對（或私鑰有密語保護但沒有提供）。",
                               "輸入正確的私鑰密語。", detail)
            if res.has("NO_SECKEY") or res.has("NEED_PASSPHRASE_SYM"):
                raise _Failure("wrong_key", "提供的私鑰都不是這個檔案的收件人。",
                               "換一把私鑰，或改用密語。", detail)
            # gpg 連收件人封包都還沒處理就失敗：多半是檔案被截斷（大檔用分段長度，讀到一半就斷）
            raise _Failure("corrupt", "檔案不完整或損壞，沒有輸出任何內容。",
                           "向提供者要一份完整的檔案。", detail)
    else:
        if not res.has("NEED_PASSPHRASE_SYM"):
            if res.has("NO_SECKEY"):
                raise _Failure("wrong_key", "這個檔案沒有用密語加密，只能用收件人的私鑰解開。",
                               "提供收件人的私鑰檔。", detail)
            raise _Failure("corrupt", "檔案不完整或損壞，沒有輸出任何內容。",
                           "向提供者要一份完整的檔案。", detail)
        if _bad_passphrase(res, "symkey"):
            raise _Failure("wrong_key", "密語不對（或檔案在開頭就損壞了）。", "確認密語後再試。", detail)
    if res.has("BEGIN_DECRYPTION") and not res.has("DECRYPTION_OKAY"):
        raise _Failure("corrupt", "檔案被截斷或損壞，沒有輸出任何內容。",
                       "向提供者要一份完整的檔案。", detail)
    if res.returncode == 0 and not res.has("BEGIN_DECRYPTION"):
        raise _Failure("unsupported_format", "這個 OpenPGP 檔案沒有加密，沒有輸出。", "", detail)
    raise _Failure("corrupt", "解密沒有完成，沒有輸出任何內容。", "", detail)


def _bad_passphrase(res: GpgResult, where: str) -> bool:
    """``where`` 是 ERROR 狀態行的位置前綴：pkdecrypt（私鑰密語）或 symkey（檔案密語）。"""
    return res.has("BAD_PASSPHRASE") or res.has("MISSING_PASSPHRASE") or any(
        code in (_GPG_ERR_BAD_PASSPHRASE, _GPG_ERR_NO_PASSPHRASE)
        for loc, code in res.error_codes() if loc.startswith(where))


def decrypt_file(
    src: PathLike,
    dst: PathLike,
    *,
    secret_key_files: Iterable[PathLike] = (),
    key_passphrase: str | None = None,
    passphrase: str | None = None,
    overwrite: bool = False,
) -> dict:
    """解開 OpenPGP 加密檔。可以給私鑰檔（可多個，私鑰有密語時給 ``key_passphrase``）、
    或檔案的密語，或兩者都給（先試私鑰、再試密語）。

    輸出先寫到目標旁邊的暫存檔，gpg 回報解密成功**而且**完整性檢查通過（GOODMDC）才換名；
    任何失敗都刪掉暫存檔，不留半成品。
    """
    src_p, dst_p = _check_src_dst(src, dst, overwrite)
    keys = _as_paths(secret_key_files, "私鑰")
    if key_passphrase == "":
        key_passphrase = None
    if key_passphrase is not None:
        check_passphrase(key_passphrase, "私鑰密語")
    if passphrase is not None:
        check_passphrase(passphrase)
    if not keys and passphrase is None:
        raise SealError("bad_input", "要給私鑰檔或密語才能解密。",
                        action="加上私鑰檔，或輸入加密時用的密語。")
    kind = pgp_kind(_read_head(src_p))
    if kind is None:
        raise SealError("unsupported_format", "這不是 OpenPGP 檔案。",
                        action="確認選對檔案；其他格式請用對應的模式解密。")
    if kind != "message":
        raise SealError("unsupported_format", "這是 OpenPGP 金鑰或簽章檔，不是加密檔。",
                        action="選要解密的 .gpg／.asc 檔。")

    info = find_gpg()
    hide = tuple(v for v in (key_passphrase, passphrase) if v)
    attempts = []
    if keys:
        # 檔案同時有密語封包時，gpg 會先拿 passphrase-fd 的值試密語封包；給空字串它會直接放棄
        # （實測：MISSING_PASSPHRASE 後不再試私鑰）。所以私鑰沒有密語時給一個隨機的假值，
        # 讓密語封包失敗後繼續用私鑰。
        attempts.append(("key", key_passphrase or secrets.token_hex(16)))
    if passphrase is not None:
        attempts.append(("passphrase", passphrase))
    failures: list[_Failure] = []
    tmp = _temp_beside(dst_p)
    try:
        for mode, pw in attempts:
            _remove(tmp)
            s = _session_with_keys(info, keys, pw)[0] if mode == "key" else GpgSession(info).__enter__()
            try:
                res = s.run(["--skip-verify", "-o", str(tmp), "--decrypt", str(src_p)],
                            passphrase=pw, timeout=timeout_for(src_p))
            finally:
                s.close()
            try:
                _check_decrypt(res, mode, hide)
            except _Failure as fail:
                _remove(tmp)
                if fail.code != "wrong_key":
                    raise SealError(fail.code, fail.reason, action=fail.action,
                                    detail=fail.detail) from None
                failures.append(fail)
                continue
            if not tmp.is_file():
                raise SealError("io_error", "gpg 回報成功，但沒有寫出檔案。", detail=res.summary(hide))
            _commit(tmp, dst_p, overwrite)
            return {
                "action": "decrypt", "format": "openpgp", "input": str(src_p),
                "output": str(dst_p), "used": mode, "bytes_out": dst_p.stat().st_size,
                "gpg": info.version,
            }
    finally:
        _remove(tmp)
    if len(failures) == 1:
        f = failures[0]
        raise SealError(f.code, f.reason, action=f.action, detail=f.detail)
    raise SealError("wrong_key", "私鑰和密語都打不開這個檔案。",
                    action="確認私鑰是收件人之一、私鑰密語與檔案密語都正確。",
                    detail=" | ".join(f"{f.reason} {f.detail}" for f in failures)[:900])
