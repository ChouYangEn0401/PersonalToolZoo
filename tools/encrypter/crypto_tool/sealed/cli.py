"""命令列：``python -m crypto_tool encrypt|decrypt|info|keygen``。

給人用，也給別的程式呼叫（加 ``--json``）。規則：

* 密語不能放在命令列引數（會留在指令歷史與行程清單）；只能從標準輸入讀，或用金鑰檔／環境變數。
* 任何輸出都不含金鑰、密語、明文。
* ``--json`` 時標準輸出只有一行 JSON：成功 ``{"ok": true, "data": {...}}``，
  失敗 ``{"ok": false, "error": {"code", "reason", "retryable", "remedy", "detail"}}``。
* 退出碼：0 成功、2 輸入有問題、3 環境問題、5 金鑰不對、6 檔案被改過或不完整、1 其他。
"""

from __future__ import annotations

import argparse
import json
import sys

from .container import AEAD_IDS
from .errors import EXIT_OK, SealError
from .keys import (
    DEFAULT_KEY_NAME, MIN_PASSPHRASE_CHARS, generate_key_file, load_key_env, load_key_file,
    passphrase_material,
)
from .ops import decrypt_path, encrypt_path, info_path

PROG = "python -m crypto_tool"


class _UsageError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message):  # argparse 預設會直接 exit(2) 並印英文到 stderr
        raise _UsageError(message)


def _add_key_options(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("金鑰來源（三選一）")
    m = g.add_mutually_exclusive_group(required=True)
    m.add_argument("--key-file", metavar="路徑",
                   help="金鑰檔：.env 風格（名稱=值）、32 bytes 二進位檔，或只有一行的文字檔")
    m.add_argument("--key-env", metavar="名稱", help="從這個名稱的環境變數讀金鑰")
    m.add_argument("--passphrase-stdin", action="store_true",
                   help="從標準輸入讀一行密語（互動時會隱藏輸入）")
    g.add_argument("--key-name", metavar="名稱",
                   help=f"金鑰檔裡要用的名稱（預設 {DEFAULT_KEY_NAME}，或檔案裡唯一的那一個）")


def build_parser() -> argparse.ArgumentParser:
    # allow_abbrev=False：不讓 --passphrase 被當成 --passphrase-stdin 的縮寫
    parser = _Parser(prog=PROG, allow_abbrev=False,
                     description="CryptoTool Pro 命令列：加密、解密檔案與資料夾。")
    sub = parser.add_subparsers(dest="command", metavar="{encrypt,decrypt,info,keygen}")
    sub.required = True
    common = _Parser(add_help=False, allow_abbrev=False)
    common.add_argument("--json", action="store_true", help="輸出一行機器可讀的 JSON")

    enc = sub.add_parser("encrypt", parents=[common], allow_abbrev=False, help="加密一個檔案或資料夾")
    enc.add_argument("input", help="要加密的檔案或資料夾")
    enc.add_argument("-o", "--output", help="輸出檔（預設：輸入名稱加上 .isd2）")
    enc.add_argument("--cipher", choices=sorted(AEAD_IDS), default="aes-256-gcm",
                     help="加密法（預設 aes-256-gcm）")
    enc.add_argument("--force", action="store_true", help="輸出檔已存在時覆蓋")
    _add_key_options(enc)

    dec = sub.add_parser("decrypt", parents=[common], allow_abbrev=False, help="解密 .isd2 檔")
    dec.add_argument("input", help="要解密的 .isd2 檔")
    dec.add_argument("-o", "--output", help="輸出位置（預設：去掉 .isd2）")
    dec.add_argument("--keep-tar", action="store_true",
                     help="內容是資料夾時不解開，輸出 .tar 檔")
    dec.add_argument("--force", action="store_true", help="輸出檔已存在時覆蓋（資料夾不會被覆蓋）")
    _add_key_options(dec)

    info = sub.add_parser("info", parents=[common], allow_abbrev=False, help="看加密檔的格式資訊（不需要金鑰）")
    info.add_argument("input", help="加密檔")

    gen = sub.add_parser("keygen", parents=[common], allow_abbrev=False, help="產生一把新的隨機金鑰，寫進金鑰檔")
    gen.add_argument("-o", "--output", required=True, help="金鑰檔要存在哪裡")
    gen.add_argument("--format", choices=["env", "raw"], default="env",
                     help="env：名稱=值 的文字檔（預設）；raw：32 bytes 二進位檔")
    gen.add_argument("--name", default=DEFAULT_KEY_NAME, help="env 格式裡的名稱")
    gen.add_argument("--force", action="store_true", help="金鑰檔已存在時覆蓋（舊金鑰會消失）")
    return parser


def _read_passphrase(confirm: bool, stdin):
    if stdin.isatty():
        import getpass
        first = getpass.getpass("密語：")
        if confirm and getpass.getpass("再輸入一次：") != first:
            raise SealError("bad_input", "兩次輸入的密語不一樣。")
        return passphrase_material(first)
    raw = stdin.buffer.readline() if hasattr(stdin, "buffer") else stdin.readline()
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise SealError("bad_input", "從標準輸入讀到的密語不是 UTF-8 編碼。",
                            action="呼叫端請用 UTF-8 把密語寫進標準輸入。") from None
    return passphrase_material(raw)


def _key_from_args(args, confirm: bool, stdin):
    if args.key_name and not args.key_file:
        raise SealError("bad_input", "--key-name 只能跟 --key-file 一起用。")
    if args.key_file:
        return load_key_file(args.key_file, args.key_name)
    if args.key_env:
        return load_key_env(args.key_env)
    return _read_passphrase(confirm, stdin)


def _dispatch(args, stdin) -> dict:
    if args.command == "encrypt":
        material = _key_from_args(args, True, stdin)
        data = encrypt_path(args.input, args.output, material,
                            cipher=args.cipher, force=args.force)
        if data.get("kdf") == "scrypt" and len(material.passphrase or "") < MIN_PASSPHRASE_CHARS:
            data["warnings"] = ["passphrase_short"]
        return data
    if args.command == "decrypt":
        material = _key_from_args(args, False, stdin)
        return decrypt_path(args.input, args.output, material,
                            force=args.force, keep_tar=args.keep_tar)
    if args.command == "info":
        return info_path(args.input)
    data = generate_key_file(args.output, fmt=args.format, name=args.name, force=args.force)
    data["action"] = "keygen"
    return data


_LABELS = {"file": "檔案", "folder": "資料夾", "tar": "tar 封存"}


def _human(data: dict) -> list[str]:
    action = data["action"]
    if action == "encrypt":
        lines = [f"已加密（{_LABELS[data['payload']]}）：{data['output']}"]
        if data.get("skipped_links"):
            lines.append(f"注意：略過了 {data['skipped_links']} 個連結／特殊檔案，它們沒有被加密。")
        if "passphrase_short" in data.get("warnings", []):
            lines.append(f"注意：密語少於 {MIN_PASSPHRASE_CHARS} 個字，容易被猜出來。")
        lines.append("提醒：金鑰或密語不見就打不開；請在這台電腦以外的地方另外留一份。")
        return lines
    if action == "decrypt":
        return [f"已解密（{_LABELS[data['payload']]}）：{data['output']}"]
    if action == "keygen":
        return [
            f"已產生金鑰檔：{data['path']}",
            f"金鑰指紋（核對備份用）：{data['key_id']}",
            "請立刻把這個檔案另外備份到這台電腦以外的地方（例如隨身碟、紙本）。",
            "金鑰檔不見，用它加密的檔案就再也打不開。",
        ]
    lines = [f"檔案：{data['input']}", f"大小：{data['size']} bytes"]
    if data["format"] == "isd2":
        lines += [f"格式：ISD2 第 {data['format_version']} 版",
                  f"加密法：{data['cipher']}",
                  "金鑰來源：" + ("密語（scrypt）" if data["kdf"] == "scrypt" else "金鑰檔（32 bytes）"),
                  f"內容：{_LABELS[data['payload']]}"]
    else:
        lines.append("格式：舊版 .isd（命令列不解密，請用視窗程式的舊版工具）")
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

    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except _UsageError as exc:
        # argparse 的訊息會把使用者打的引數原樣帶出來（可能是誤放的密語），所以不轉述
        return fail(SealError("bad_input", "指令的寫法不對。",
                              action=f"執行 {PROG} --help 看用法。", detail="usage"))
    try:
        data = _dispatch(args, stdin)
    except SealError as err:
        return fail(err)
    except KeyboardInterrupt:
        return fail(SealError("bad_input", "已取消。"))
    except Exception as exc:  # 不印訊息內容：例外文字可能帶路徑以外的資料
        return fail(SealError("internal_bug", "程式發生沒預期到的錯誤。",
                              action="把代碼與 detail 回報給維護者。",
                              detail=type(exc).__name__))
    if want_json:
        _emit(stdout, json.dumps({"ok": True, "data": data}))
    else:
        for line in _human(data):
            _emit(stdout, line)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
