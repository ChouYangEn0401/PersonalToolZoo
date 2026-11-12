"""age v1 檔案格式（c2sp.org/age）的自寫實作，只用 ``cryptography`` 的標準原語。

產生的檔案可以用任何 age／rage 工具解開；同一份密文可以有多個收件人（萬用鎖）。
支援：X25519 金鑰、scrypt 密語、ASCII armor、身分檔（含密語保護）。
不支援：外掛（plugin）、SSH 金鑰、後量子與硬體標籤收件人。

這是自己寫的實作，通過 C2SP CCTV 官方測試向量，但未經外部審閱。詳見 docs/format-age.md。
錯誤一律丟 ``crypto_tool.sealed.errors.SealError``。
"""

from .api import (
    AgeInfo, DecryptResult, EncryptResult, decrypt_bytes, decrypt_file,
    decrypt_stream, detect, encrypt_bytes, encrypt_file, encrypt_stream, inspect, is_age,
)
from .armor import BEGIN as ARMOR_BEGIN, END as ARMOR_END
from .identityfile import (
    format_identity_file, is_encrypted_identity_file, load_identity_file, parse_identity_file,
    write_identity_file,
)
from .recipients import (
    DEFAULT_SCRYPT_WORK_FACTOR, MAX_SCRYPT_WORK_FACTOR, ScryptIdentity, ScryptRecipient,
    X25519Identity, X25519Recipient, generate_identity, parse_identity, parse_recipient,
    passphrase_identity, passphrase_recipient,
)

EXTENSION = ".age"


def parse_recipients(text: str) -> list[X25519Recipient]:
    """解讀收件人清單（一行一把 age1 公鑰；空行與 # 開頭的行略過）。"""
    out: list[X25519Recipient] = []
    for line in str(text).splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            r = parse_recipient(line)
            if r not in out:
                out.append(r)
    if not out:
        parse_recipient("")  # 丟 key_missing
    return out


__all__ = [
    "ARMOR_BEGIN", "ARMOR_END", "AgeInfo", "DEFAULT_SCRYPT_WORK_FACTOR", "DecryptResult",
    "EXTENSION", "EncryptResult", "MAX_SCRYPT_WORK_FACTOR", "ScryptIdentity",
    "ScryptRecipient", "X25519Identity", "X25519Recipient", "decrypt_bytes", "decrypt_file",
    "decrypt_stream", "detect", "encrypt_bytes", "encrypt_file", "encrypt_stream",
    "format_identity_file", "generate_identity", "inspect", "is_age", "is_encrypted_identity_file",
    "load_identity_file", "parse_identity", "parse_identity_file", "parse_recipient",
    "parse_recipients", "passphrase_identity", "passphrase_recipient",
    "write_identity_file",
]
