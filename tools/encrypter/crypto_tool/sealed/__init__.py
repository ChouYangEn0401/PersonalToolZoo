"""Encrypter 0.4.0 的核心：命令列、整合層（workflow）、設定，以及 ISD2 預覽格式（已停用，只能解密）。

* 現行的兩種公開格式在 ``agefmt``（age v1）與 ``pgpmode``（OpenPGP），由 ``workflow`` 串起來。
* ``container``／``ops``／``keys``：ISD2 預覽格式（已停用）——只保留解密與看資訊。
* 跟 ``core/``（舊版 .isd、Mixture）完全分開：這裡只依賴 ``cryptography``，不 import ``core``。

套件內部一律用相對 import，所以不管是 ``crypto_tool.sealed`` 還是把 ``crypto_tool/`` 放進
``sys.path`` 後的 ``sealed`` 都能用。
"""

from .container import EXTENSION, KeyMaterial
from .errors import SealError
from .keys import load_key_env, load_key_file, passphrase_material, parse_secret_value
from .ops import decrypt_path, default_decrypt_output, info_path

__all__ = [
    "EXTENSION", "KeyMaterial", "SealError",
    "load_key_env", "load_key_file", "passphrase_material", "parse_secret_value",
    "decrypt_path", "default_decrypt_output", "info_path",
]
