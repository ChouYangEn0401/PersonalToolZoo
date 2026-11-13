"""命令列：``python -m crypto_tool <指令> ...``。

指令：``encrypt``、``decrypt``、``inspect``（舊名 ``info`` 也可以）、``keygen``、``rewrap``、``rekey``；
另有 ``--check``（離線自我檢查）與 ``--version``。

給人用，也給別的程式呼叫（加 ``--json``）。規則：

* **任何參數都不能直接放密語**（會留在指令歷史與行程清單）：密語只從終端機互動輸入（隱藏），
  或標準輸入讀一行（``--passphrase-stdin``；被導向時 ``--passphrase`` 也一樣從標準輸入讀）。
* 需要好幾個密語時，從標準輸入依序一行一個：
  ① 有密語保護的身分檔（依 ``-i`` 的順序，只有真的需要時才讀）② PGP 私鑰的密語（``--pgp-key-passphrase``）
  ③ 檔案密語（``--passphrase``）④ 新密語（``--new-passphrase``、``keygen --protect``）。
* 任何輸出都不含金鑰、密語、明文；argparse 的錯誤訊息會轉述使用者打的引數，所以不轉述。
* ``--json`` 時標準輸出只有一行 JSON：成功 ``{"ok": true, "data": {...}}``，
  失敗 ``{"ok": false, "error": {"code", "reason", "retryable", "remedy", "detail"}}``。
* 退出碼：0 成功、2 輸入有問題、3 環境問題、5 金鑰不對、6 檔案被改過或不完整、1 其他。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import settings, workflow
from .errors import EXIT_ENVIRONMENT, EXIT_OK, SealError
from .keys import MIN_PASSPHRASE_CHARS, load_key_env, load_key_file

PROG = "python -m crypto_tool"
COMMANDS = ("encrypt", "decrypt", "inspect", "info", "keygen", "rewrap", "rekey")


class _UsageError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message):  # argparse 預設會直接 exit(2) 並印英文到 stderr
        raise _UsageError(message)


def _passphrase_flags(p, *, what: str = "檔案") -> None:
    g = p.add_mutually_exclusive_group()
    g.add_argument("--passphrase", action="store_true",
                   help=f"用{what}密語：在終端機隱藏輸入（被導向時從標準輸入讀一行）。不能把密語寫在參數裡")
    g.add_argument("--passphrase-stdin", action="store_true",
                   help=f"用{what}密語：從標準輸入讀一行（UTF-8）")


def _identity_flags(p) -> None:
    p.add_argument("-i", "--identity", action="append", default=[], metavar="身分檔",
                   help="能開鎖的鑰匙檔：age 身分檔（可為密語保護）或 OpenPGP 私鑰 .asc；可給多個")
    p.add_argument("--pgp-secret", action="append", default=[], metavar="私鑰.asc",
                   help="OpenPGP 私鑰檔（可給多個；-i 也認得 OpenPGP 私鑰）")
    p.add_argument("--pgp-key-passphrase", action="store_true",
                   help="OpenPGP 私鑰有密語保護：互動或從標準輸入讀它的密語")


def _recipient_flags(p, *, pgp: bool = True) -> None:
    p.add_argument("-r", "--recipient", action="append", default=[], metavar="age1…",
                   help="簡單模式的收件人公鑰（可給多個）")
    p.add_argument("-R", "--recipients-file", action="append", default=[], metavar="檔案",
                   help="收件人清單檔：一行一把 age1 公鑰（# 開頭是註解）；也接受自己的身分檔（用它的公鑰）")
    p.add_argument("--with-master", action="store_true",
                   help="也讓設定好的萬用鎖（全部）打得開（.env 的 ENCRYPTER_MASTER_RECIPIENT／ENCRYPTER_MASTER_PGP_KEY）")
    p.add_argument("--master", action="append", default=[], metavar="萬用鎖",
                   help="這次直接指定一把萬用鎖，可以重複給好幾把：簡單模式是 age1 公鑰或公鑰清單檔，"
                        "PGP 模式是公鑰 .asc 檔")
    if pgp:
        p.add_argument("--pgp-recipient", action="append", default=[], metavar="公鑰.asc",
                       help="PGP 模式的收件人公鑰檔（可給多個）")


def build_parser() -> argparse.ArgumentParser:
    # allow_abbrev=False：不讓縮寫的參數被誤認成別的參數
    parser = _Parser(prog=PROG, allow_abbrev=False,
                     description="CryptoTool Pro 命令列：用公開標準格式（age／OpenPGP）加密、解密檔案與資料夾。")
    sub = parser.add_subparsers(dest="command", metavar="{encrypt,decrypt,inspect,keygen,rewrap,rekey}")
    sub.required = True
    common = _Parser(add_help=False, allow_abbrev=False)
    common.add_argument("--json", action="store_true", help="輸出一行機器可讀的 JSON")

    def add(name, help_text):
        return sub.add_parser(name, parents=[common], allow_abbrev=False, help=help_text)

    enc = add("encrypt", "加密一個或多個檔案／資料夾（多個或資料夾會先打包成 tar）")
    enc.add_argument("inputs", nargs="+", metavar="輸入", help="要加密的檔案或資料夾")
    enc.add_argument("-o", "--output", help="輸出檔（只有一個輸入時可省略：名稱加上 .age／.gpg）")
    enc.add_argument("--mode", choices=workflow.MODES, default=workflow.MODE_AGE,
                     help="age＝簡單模式（預設）；pgp＝OpenPGP（需要系統有 gpg）")
    _recipient_flags(enc)
    _passphrase_flags(enc)
    enc.add_argument("--armor", action="store_true", help="輸出文字形式（可以貼在信件或文字檔裡）")
    enc.add_argument("--force", action="store_true", help="輸出檔已存在時覆蓋")

    dec = add("decrypt", "解密（自動辨識 age／OpenPGP／ISD2 預覽格式）")
    dec.add_argument("input", help="要解密的檔案")
    dec.add_argument("-o", "--output", help="輸出位置（預設：去掉 .age／.gpg／.asc；資料夾另去掉 .tar）")
    _identity_flags(dec)
    _passphrase_flags(dec)
    dec.add_argument("--all-layers", action="store_true",
                     help="一路解到底：解開後還是加密檔（或資料夾最上層有加密檔）就用同一組鑰匙繼續解")
    dec.add_argument("--keep-tar", action="store_true", help="內容是資料夾時不解開，輸出 .tar 檔")
    dec.add_argument("--force", action="store_true", help="輸出檔已存在時覆蓋（資料夾不會被覆蓋）")
    old = dec.add_argument_group("ISD2 預覽格式（已停用）專用：只為了解開舊檔")
    m = old.add_mutually_exclusive_group()
    m.add_argument("--key-file", metavar="路徑", help="（已停用格式）ISD2 預覽格式的金鑰檔")
    m.add_argument("--key-env", metavar="名稱", help="（已停用格式）從這個名稱的環境變數讀 ISD2 預覽格式的金鑰")
    old.add_argument("--key-name", metavar="名稱", help="（已停用格式）金鑰檔裡要用的名稱")

    for name in ("inspect", "info"):
        info = add(name, "看加密檔的資訊（不需要金鑰）" if name == "inspect" else "inspect 的舊名")
        info.add_argument("input", help="加密檔")

    gen = add("keygen", "產生新的金鑰（age 身分檔，或 OpenPGP 金鑰對）")
    gen.add_argument("--mode", choices=workflow.MODES, default=workflow.MODE_AGE)
    gen.add_argument("-o", "--output",
                     help=f"age：身分檔路徑（預設 {workflow.DEFAULT_IDENTITY_NAME}）；"
                          f"pgp：檔名開頭（預設 {workflow.DEFAULT_PGP_PREFIX} → .public.asc／.secret.asc）")
    gen.add_argument("--protect", action="store_true", help="用密語保護私鑰（互動輸入兩次，或從標準輸入讀一行）")
    gen.add_argument("--name", default="Encrypter key", help="pgp：金鑰上的名稱")
    gen.add_argument("--email", help="pgp：金鑰上的信箱（可省略）")
    gen.add_argument("--key-type", choices=("ed25519", "rsa3072", "rsa4096"), default="ed25519",
                     help="pgp：金鑰種類（預設 ed25519；要給很舊的程式用時選 rsa）")
    gen.add_argument("--force", action="store_true", help="檔案已存在時覆蓋（舊金鑰會消失）")

    for name, text in (("rewrap", "換鎖（只限 age）：換一組收件人，內容位元組不變"),
                       ("rekey", "換檔案金鑰：解開後用新的收件人整份重新加密")):
        p = add(name, text)
        p.add_argument("input", help="要換鎖的加密檔")
        p.add_argument("-o", "--output", required=True, help="輸出檔")
        _identity_flags(p)
        _passphrase_flags(p, what="舊的檔案")
        _recipient_flags(p, pgp=(name == "rekey"))
        p.add_argument("--new-passphrase", action="store_true", help="新的鎖用密語（互動輸入兩次或從標準輸入讀）")
        p.add_argument("--armor", action="store_true", help="輸出文字形式（預設沿用來源的形式）")
        p.add_argument("--force", action="store_true", help="輸出檔已存在時覆蓋")
    return parser


# ── 祕密的來源 ──────────────────────────────────────────────────────────

class Secrets:
    """問密語：終端機就隱藏輸入；被導向就從標準輸入一行一個依序讀。"""

    def __init__(self, stdin, stderr):
        self.stdin = stdin
        self.stderr = stderr

    def ask(self, prompt: str, *, confirm: bool = False) -> str:
        if self.stdin.isatty():
            import getpass
            first = getpass.getpass(prompt + "：")
            if confirm and getpass.getpass("再輸入一次：") != first:
                raise SealError("bad_input", "兩次輸入的密語不一樣。")
            value = first
        else:
            raw = self.stdin.buffer.readline() if hasattr(self.stdin, "buffer") else self.stdin.readline()
            if isinstance(raw, bytes):
                try:
                    raw = raw.decode("utf-8-sig")
                except UnicodeDecodeError:
                    raise SealError("bad_input", "從標準輸入讀到的密語不是 UTF-8 編碼。",
                                    action="呼叫端請用 UTF-8 把密語寫進標準輸入。") from None
            value = raw.rstrip("\r\n")
        if not value:
            raise SealError("key_missing", f"沒有輸入{prompt}。")
        return value


def _keyring(args, secrets: Secrets, *, allow_defaults: bool) -> workflow.Keyring:
    """依參數讀鑰匙。順序固定（身分檔密語 → PGP 私鑰密語 → 檔案密語），標準輸入就照這個順序讀。"""
    ring = workflow.Keyring()
    id_files = list(getattr(args, "identity", []))
    pgp_files = [Path(p) for p in getattr(args, "pgp_secret", [])]
    wants_pass = bool(getattr(args, "passphrase", False) or getattr(args, "passphrase_stdin", False))
    key_file = getattr(args, "key_file", None)
    key_env = getattr(args, "key_env", None)
    key_name = getattr(args, "key_name", None)
    if key_name and not key_file:
        raise SealError("bad_input", "--key-name 只能跟 --key-file 一起用。")
    if allow_defaults and not (id_files or pgp_files or wants_pass or key_file or key_env):
        default_age, default_pgp = workflow.default_keyring_paths()
        id_files, pgp_files = default_age, default_pgp
    ages, pgps = workflow.load_identities(
        id_files, lambda path: secrets.ask(f"身分檔 {Path(path).name} 的密語"))
    ring.age_identities = ages
    ring.pgp_secret_keys = pgps + [p for p in pgp_files if p not in pgps]
    for p in ring.pgp_secret_keys:
        if not p.is_file():
            raise SealError("key_missing", "找不到 OpenPGP 私鑰檔。", action="確認 --pgp-secret 的路徑。")
    if getattr(args, "pgp_key_passphrase", False):
        ring.pgp_key_passphrase = secrets.ask("OpenPGP 私鑰的密語")
    if wants_pass:
        ring.passphrase = secrets.ask("密語")
    if key_file:
        ring.isd2_material = load_key_file(key_file, key_name)
    elif key_env:
        ring.isd2_material = load_key_env(key_env)
    return ring


def _recipients(args, *, mode: str, use_passphrase: bool) -> workflow.Recipients:
    return workflow.resolve_recipients(
        mode, recipients=args.recipient, recipient_files=args.recipients_file,
        with_master=args.with_master, pgp_recipient_files=getattr(args, "pgp_recipient", []),
        use_passphrase=use_passphrase, masters=args.master)


def _dispatch(args, secrets: Secrets) -> dict:
    cmd = args.command
    if cmd == "encrypt":
        wants_pass = args.passphrase or args.passphrase_stdin
        recips = _recipients(args, mode=args.mode, use_passphrase=wants_pass)   # 先檢查組合，再問密語
        passphrase = secrets.ask("密語", confirm=True) if wants_pass else None
        return workflow.encrypt(args.inputs, args.output, recipients=recips, passphrase=passphrase,
                                armor=args.armor, force=args.force)
    if cmd == "decrypt":
        ring = _keyring(args, secrets, allow_defaults=True)
        if args.all_layers:
            if args.keep_tar:
                raise SealError("bad_input", "--all-layers 要解開資料夾才能往裡面找，不能跟 --keep-tar 一起用。")
            return workflow.decrypt_all_layers(args.input, args.output, ring, force=args.force)
        return workflow.decrypt(args.input, args.output, ring, force=args.force, keep_tar=args.keep_tar)
    if cmd in ("inspect", "info"):
        return workflow.inspect(args.input)
    if cmd == "keygen":
        passphrase = secrets.ask("保護私鑰的密語", confirm=True) if args.protect else None
        if args.mode == workflow.MODE_AGE:
            return workflow.keygen_age(args.output, passphrase=passphrase, force=args.force)
        return workflow.keygen_pgp(args.output, name=args.name, email=args.email, passphrase=passphrase,
                                   key_type=args.key_type, force=args.force)
    # rewrap / rekey
    src_fmt = workflow.detect_format(args.input)
    mode = workflow.MODE_PGP if src_fmt == workflow.FMT_PGP else workflow.MODE_AGE
    if cmd == "rewrap" and src_fmt == workflow.FMT_PGP:
        raise SealError("unsupported_format", "OpenPGP 檔不能只換鎖（gpg 沒有這個功能）。",
                        action="改用 rekey：解開後用新的收件人整份重新加密。")
    recips = _recipients(args, mode=mode, use_passphrase=args.new_passphrase)
    ring = _keyring(args, secrets, allow_defaults=True)
    new_pass = secrets.ask("新的密語", confirm=True) if args.new_passphrase else None
    armor = True if args.armor else None
    func = workflow.rewrap if cmd == "rewrap" else workflow.rekey
    return func(args.input, args.output, ring, recips, new_passphrase=new_pass, armor=armor, force=args.force)


# ── 給人看的輸出 ────────────────────────────────────────────────────────

_PAYLOAD = {"file": "檔案", "folder": "資料夾", "tar": "tar 封存"}


def _lock_text(lock: dict) -> str:
    parts = [workflow.FORMAT_LABELS.get(lock.get("format"), str(lock.get("format")))]
    types = lock.get("recipient_types") or {}
    for kind, n in types.items():
        parts.append("密語" if kind == "scrypt" else f"{kind} 金鑰 {n} 把")
    if lock.get("recipient_key_ids"):
        parts.append("OpenPGP 收件人 " + "、".join(lock["recipient_key_ids"]))
    if lock.get("format") == workflow.FMT_PGP and lock.get("passphrase"):
        parts.append("也可用密語")
    return "，".join(parts)


def _human(data: dict) -> list[str]:
    action = data["action"]
    if action == "encrypt":
        label = workflow.FORMAT_LABELS[data["format"]]
        lines = [f"已加密（{label}，{_PAYLOAD[data['payload']]}）：{data['output']}"]
        r = data["recipients"]
        who = []
        if r["keys"]:
            who.append(f"{r['keys']} 把金鑰")
        if r["passphrase"]:
            who.append("密語")
        masters = r.get("masters", 1 if r["master"] else 0)
        lines.append("可以打開的鑰匙：" + "、".join(who) + (f"（含萬用鎖 {masters} 把）" if r["master"] else ""))
        if data.get("skipped_links"):
            lines.append(f"注意：略過了 {data['skipped_links']} 個連結／特殊檔案，它們沒有被加密。")
        if "passphrase_short" in data.get("warnings", []):
            lines.append(f"注意：密語少於 {MIN_PASSPHRASE_CHARS} 個字，容易被猜出來。")
        lines.append("提醒：鑰匙或密語不見就打不開；請在這台電腦以外的地方另外留一份。")
        return lines
    if action == "decrypt":
        lines = [f"已解密（{workflow.FORMAT_LABELS.get(data['format'], data['format'])}，"
                 f"{_PAYLOAD[data['payload']]}）：{data['output']}"]
        if data.get("used_master"):
            lines.append("用的是萬用鎖。")
        if data.get("deprecated"):
            lines.append("注意：ISD2 預覽格式已停用；建議把內容改用簡單模式或 PGP 模式重新加密。")
        if data.get("all_layers"):
            lines.append(f"一共解開 {len(data['layers'])} 層（最深第 {data['depth']} 層）。")
            for stop in data["stopped"]:
                where = stop["path"]
                if stop["reason"] == "needs_other_key":
                    lines.append(f"第 {stop['depth']} 層需要別的鑰匙：{where}（{_lock_text(stop['lock'])}）")
                elif stop["reason"] == "depth_limit":
                    lines.append(f"第 {stop['depth']} 層超過上限（{workflow.MAX_LAYERS} 層），沒有再往下解：{where}")
                elif stop["reason"] == "too_many_items":
                    lines.append(f"內層加密檔太多，第 {stop['depth']} 層的 {where} 沒有再解。")
                else:
                    lines.append(f"第 {stop['depth']} 層解不開：{where}（{stop.get('message', '')}）")
            if data["complete"]:
                lines.append("已經解到底，沒有剩下的加密檔。")
        return lines
    if action == "keygen":
        if data["mode"] == workflow.MODE_AGE:
            lines = [f"已產生 age 身分檔：{data['path']}",
                     f"公鑰（給別人加密用，可以公開）：{data['public_key']}"]
            lines.append("私鑰有密語保護。" if data["protected"] else "注意：私鑰沒有密語保護，拿到檔案的人就能解密。")
        else:
            lines = [f"已產生 OpenPGP 金鑰對：公鑰 {data['public_key']}、私鑰 {data['secret_key']}",
                     f"指紋：{data['fingerprint']}"]
            if data.get("warning"):
                lines.append("注意：" + data["warning"])
        lines += ["請立刻把私鑰另外備份到這台電腦以外的地方（例如隨身碟、紙本）。",
                  "私鑰不見，用它加密的檔案就再也打不開（除非也加了萬用鎖）。"]
        return lines
    if action in ("rewrap", "rekey"):
        lines = [f"已{'換鎖' if action == 'rewrap' else '換檔案金鑰並重新加密'}：{data['output']}"]
        if action == "rewrap":
            lines.append("內容位元組沒有變，只換了誰能打開。注意：已經被複製走的舊檔，舊鑰匙仍然打得開；"
                         "要讓舊鑰匙真的失效請用 rekey，並刪掉舊副本。")
        else:
            lines.append("檔案金鑰已換新；之後只有新的收件人打得開這個新檔。已經流出去的舊檔不受影響。")
        return lines
    if action == "check":
        gpg = data["gpg"]
        lines = [f"Python {data['python']}，cryptography {data['cryptography'] or '（沒有安裝）'}",
                 "簡單模式（age）：" + ("可以用" if data["ok"] else "不能用"),
                 "PGP 模式：" + (f"可以用（gpg {gpg['version']}）" if gpg["available"] else f"不能用：{gpg['reason']}")]
        master = data["settings"].get(settings.MASTER_RECIPIENT, {})
        count = master.get("count", 1 if master.get("set") else 0)
        lines.append("萬用鎖：" + (f"已設定 {count} 把" if master.get("set") else "沒有設定"))
        return lines
    # inspect
    fmt = data.get("format")
    lines = [f"檔案：{data['input']}", f"大小：{data['size']} bytes",
             f"格式：{workflow.FORMAT_LABELS.get(fmt, fmt)}"]
    if fmt == workflow.FMT_AGE:
        counts = data.get("stanza_counts", {})
        lines.append("收件人：" + "、".join(("密語" if k == "scrypt" else f"{k} ×{n}") for k, n in counts.items()))
        lines.append("文字形式：" + ("是" if data.get("armored") else "否"))
    elif fmt == workflow.FMT_PGP:
        if data.get("details_unavailable"):
            lines.append(data["note"])
        else:
            ids = [r.get("key_id") for r in data.get("recipients", [])]
            lines.append("收件人：" + ("、".join(ids) if ids else "（沒有金鑰收件人）"))
            lines.append("也可用密語：" + ("是" if data.get("has_passphrase") else "否"))
    elif fmt == workflow.FMT_ISD2:
        lines += [f"加密法：{data['cipher']}",
                  "金鑰來源：" + ("密語（scrypt）" if data["kdf"] == "scrypt" else "金鑰檔（32 bytes）"),
                  data["note"]]
    else:
        lines.append("舊版格式；命令列不解密，請用視窗程式的舊版工具。")
    return lines


def _emit(stream, text: str) -> None:
    try:
        stream.write(text + "\n")
    except UnicodeEncodeError:  # 主控台編碼印不出某些字
        encoding = getattr(stream, "encoding", None) or "ascii"
        stream.write(text.encode(encoding, "replace").decode(encoding) + "\n")
    stream.flush()


def main(argv=None, *, stdin=None, stdout=None, stderr=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    stdin = sys.stdin if stdin is None else stdin
    stdout = sys.stdout if stdout is None else stdout
    stderr = sys.stderr if stderr is None else stderr
    want_json = "--json" in argv

    def fail(err: SealError) -> int:
        if want_json:
            _emit(stdout, json.dumps({"ok": False, "error": err.to_dict()}))
        else:
            _emit(stderr, f"失敗：{err.reason}")
            if err.action:
                _emit(stderr, f"怎麼辦：{err.action}")
            _emit(stderr, f"（代碼 {err.code}，退出碼 {err.exit_code}）")
        return err.exit_code

    def done(data: dict) -> int:
        if want_json:
            _emit(stdout, json.dumps({"ok": True, "data": data}))
        else:
            for line in _human(data):
                _emit(stdout, line)
        return EXIT_OK

    try:
        settings.load_into_environ()
    except Exception:  # noqa: BLE001 - 讀設定失敗不該讓命令列打不開
        pass
    if argv and argv[0] in ("--check", "--version"):
        if any(a not in ("--check", "--version", "--json") for a in argv):
            return fail(SealError("bad_input", "指令的寫法不對。", action=f"執行 {PROG} --help 看用法。",
                                  detail="usage"))
        if argv[0] == "--version":
            try:
                from .._version import __version__
            except ImportError:  # pragma: no cover - 頂層載入時
                from _version import __version__
            if want_json:
                return done({"action": "version", "version": __version__})
            _emit(stdout, f"CryptoTool Pro {__version__}")
            return EXIT_OK
        data = workflow.self_check()
        done(data)
        return EXIT_OK if data["ok"] else EXIT_ENVIRONMENT

    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except _UsageError:
        # argparse 的訊息會把使用者打的引數原樣帶出來（可能是誤放的密語），所以不轉述
        return fail(SealError("bad_input", "指令的寫法不對。",
                              action=f"執行 {PROG} --help 看用法。", detail="usage"))
    try:
        data = _dispatch(args, Secrets(stdin, stderr))
    except SealError as err:
        return fail(err)
    except KeyboardInterrupt:
        return fail(SealError("bad_input", "已取消。"))
    except Exception as exc:  # 不印訊息內容：例外文字可能帶路徑以外的資料
        return fail(SealError("internal_bug", "程式發生沒預期到的錯誤。",
                              action="把代碼與 detail 回報給維護者。",
                              detail=type(exc).__name__))
    return done(data)


if __name__ == "__main__":
    sys.exit(main())
