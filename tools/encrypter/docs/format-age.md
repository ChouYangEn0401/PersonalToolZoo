# age 格式實作說明（`crypto_tool/agefmt`）

> **自寫實作、通過官方測試向量、未經外部審閱。**
> 程式碼是照公開規格自己寫的，用 C2SP CCTV 的官方測試向量與大量負向測試驗證過，
> 但沒有經過第三方的密碼學審閱。產生的檔案是標準 age v1，任何 age／rage 都能解；
> 萬一這個工具出問題，用官方工具一樣打得開。

## 1. 照哪份規格

| 項目 | 依據 |
|---|---|
| 檔案格式 | age v1 規格，C2SP 編輯版 <https://github.com/C2SP/C2SP/blob/main/age.md>（穩定版 <https://c2sp.org/age>、<https://age-encryption.org/v1>） |
| Bech32 | BIP-173，照 age 規格「資料部分沒有長度上限」 |
| base64 | RFC 4648 標準字母、無 padding、必須是正規形式（armor 內除外：armor 用有 padding 的正規形式） |
| HKDF | RFC 5869（SHA-256） |
| scrypt | RFC 7914 |
| ChaCha20-Poly1305 | RFC 7539／8439 |
| X25519 | RFC 7748 |
| ASCII armor | RFC 7468 第 3 節的嚴格 PEM，標籤 `AGE ENCRYPTED FILE` |
| 細節對照 | age 參考實作（Go，`filippo.io/age`）的公開原始碼，只當閱讀資料，沒有執行 |

密碼學原語全部來自 `cryptography` 套件（42 版起就有的 API：X25519、ChaCha20Poly1305、HKDF、HMAC、Scrypt），
這裡只負責照規格把它們接起來，沒有自創任何原語或格式變化。Bech32 是文字編碼（不是密碼學），照 BIP-173 自己寫。

## 2. 支援範圍

**支援**

- 標頭：版本行 `age-encryption.org/v1`、收件人區塊（stanza，本體 64 字折行、最後一行必短於 64 字）、
  `---` MAC 行（HMAC-SHA-256，鍵為 HKDF(file key, salt=空, info="header")）。
- 收件人／身分：
  - X25519：公鑰 `age1…`、私鑰 `AGE-SECRET-KEY-1…`。
  - scrypt（密語）：加密預設 work factor **18**（2^18，與 age 參考實作相同）；
    解密接受上限 **22**（與 age 參考實作 `NewScryptIdentity` 的預設上限相同，查證自其 `scrypt.go`），
    超過就在計算之前拒絕，不會耗用記憶體。上限可以用 `passphrase_identity(..., max_work_factor=)` 調低。
    我們自己加密時最高只允許到 22，避免產生自己預設打不開的檔案。
- 內容：STREAM（ChaCha20-Poly1305、64 KiB 分塊、16 位元組 nonce、payload key = HKDF(file key, salt=nonce, info="payload")、
  11 位元組大端序計數器＋最後一塊旗標）。截斷、加料、對調、重複、空的最後一塊都會被拒絕。
- ASCII armor 讀寫（前後空白、CRLF 允許；其餘一律嚴格）。
- 多收件人（萬用鎖）：同一份密文，任一把鑰匙都能開；每多一把 X25519 收件人，標頭只多約 100 位元組。
- 身分檔：`age-keygen` 格式（`# created:`、`# public key:` 註解行＋私鑰行），可放多把；
  讀取時也接受 `.env` 風格 `NAME=AGE-SECRET-KEY-1…`（可加 `export`、引號；其他 `NAME=值` 略過），寫出一律用 age-keygen 格式。
- 密語保護的身分檔：內容就是「以 scrypt 收件人加密的 age 檔」（age 的標準做法，`age -d -i` 會要求輸入密語），
  二進位或 armor 都可以讀；寫出時預設用 armor。
- 換鎖 `rewrap` 與換檔案金鑰 `rekey`（見第 4 節）。
- 解密時忽略不認得的收件人區塊（grease）。

**規格裡的嚴格規則（都有測試）**

- base64 必須無 padding 且是正規形式；任何 CR 都拒絕（標頭只能用 LF）。
- 引數是 1 個以上的可見 ASCII（33～126），用單一空白分隔。
- X25519 區塊：必須剛好 2 個引數（含類型），臨時公鑰是 32 位元組的正規 base64，本體必須剛好 32 位元組（在解密前檢查），
  共享祕密全零（低階點）時中止。
- scrypt 區塊：必須剛好 3 個引數，salt 是 16 位元組的正規 base64，work factor 必須符合 `^[1-9][0-9]*$`，本體必須剛好 32 位元組。
- **scrypt 區塊必須是唯一的區塊**：加密時拒絕密語和其他收件人混用（`bad_input`）；
  解密時只要標頭裡 scrypt 和其他區塊並存就拒絕，不論手上是哪一種鑰匙（比參考實作嚴格一點，符合規格的意圖）。
- 標頭上限 2 MiB、最多 1024 個區塊（與參考實作相同）。

**不支援**

- 外掛（plugin，`AGE-PLUGIN-…`）、SSH 金鑰收件人、後量子 `age1pq…`／`mlkem768x25519`、硬體標籤 `age1tag…`／`age1tagpq…`。
  遇到時回報 `unsupported_format`，並建議改用 X25519 金鑰或官方工具。
- 標頭裡的任何自訂擴充。
- 依位置隨機讀取（seek）；只做循序串流。

## 3. API（給整合用）

```text
generate_identity() -> X25519Identity
parse_recipient(s) -> X25519Recipient            parse_recipients(text) -> list
parse_identity(s) -> X25519Identity
passphrase_recipient(passphrase, work_factor=18) / passphrase_identity(passphrase, max_work_factor=22)
parse_identity_file(text_or_bytes, passphrase_provider=None) -> list[X25519Identity]
load_identity_file(path, passphrase_provider=None) -> list[X25519Identity]
format_identity_file(identities, *, created=None) -> str
write_identity_file(path, identities, *, passphrase=None, armor=True, overwrite=False, work_factor=18)
is_encrypted_identity_file(data) -> bool
encrypt_stream(src, dst, recipients, *, armor=False, progress=None) -> EncryptResult
decrypt_stream(src, dst, identities, *, armor=None, progress=None) -> DecryptResult
encrypt_file(src, dst, recipients, *, armor=False, overwrite=False, progress=None) -> EncryptResult
decrypt_file(src, dst, identities, *, overwrite=False, progress=None) -> DecryptResult
inspect(path) -> AgeInfo
rewrap(src, dst, identities, new_recipients, *, armor=None, overwrite=False, verify_payload=True) -> RewrapResult
rekey(src, dst, identities, new_recipients, *, armor=None, overwrite=False, progress=None) -> EncryptResult
is_age(head_bytes) -> bool        detect(head_bytes) -> "binary" | "armor" | None
encrypt_bytes / decrypt_bytes（小資料用）
```

- `recipients` 可以混用 `X25519Recipient`、`age1…` 字串、`X25519Identity`（取其公鑰）或一個 `ScryptRecipient`；重複的會合併。
- `identities` 是 `X25519Identity`、`AGE-SECRET-KEY-1…` 字串或 `ScryptIdentity` 的清單，依序嘗試。
- 檔案層 `progress(done, total)`；串流層 `progress(done)`。
- `decrypt_stream` 會邊驗證邊寫出已驗證的分塊；出錯時呼叫端的 `dst` 可能已有前段。要「全有或全無」請用 `decrypt_file`：
  它寫到同資料夾的暫存檔（`.名稱.partial-xxxx`，權限 0600）、fsync，全部驗證通過才原子換名；失敗或中斷時刪除暫存檔。
- 結果物件（`EncryptResult`、`DecryptResult`、`RewrapResult`、`AgeInfo`）只含公開資訊；有 `to_dict()`。
  私鑰、密語物件的 `repr`／`str` 都遮蔽祕密，也不能 pickle；取出私鑰文字要明確呼叫 `secret_key_string()`。
- `is_age` 建議傳檔案開頭至少 1100 位元組（armor 前面可以有最多 1024 位元組空白）；其他版本的 age 檔也回傳 True，解密時再說明不支援。
- `inspect` 不需要金鑰；`plaintext_size` 由大小推算，只能抓到「大小不可能」的截斷（例如最後一塊剩 0～16 位元組），
  在最後一塊中間截斷要解密時才會發現。

### 錯誤

一律丟 `crypto_tool.sealed.errors.SealError`，只用既有的代碼；`reason`／`action` 是給人看的中文，不含金鑰、密語或明文，
`detail` 是穩定的機器用字串：

| 情況 | code | detail |
|---|---|---|
| 不是 age 檔、空檔、其他版本 | `unsupported_format` | `header:not-age`、`header:empty`、`header:unsupported-version` |
| 標頭格式錯（含 scrypt 混用、低階點、長度不對） | `corrupt` | `header:…` |
| scrypt work factor 超過上限 | `unsupported_format` | `header:scrypt-work-factor-too-large` |
| armor 格式錯 | `corrupt` | `armor:…` |
| 標頭 MAC 不符 | `corrupt` | `hmac` |
| 內容被截斷、改過、多了資料 | `corrupt` | `payload:…` |
| 沒有一把鑰匙打得開 | `wrong_key` | `no-match` |
| 沒給鑰匙、密語空白、加密身分檔沒給密語 | `key_missing` | |
| 公鑰／私鑰／身分檔格式錯 | `bad_key_format` | |
| 密語與其他收件人混用、換鎖改成密語 | `bad_input` | `scrypt-not-alone`、`rewrap-to-scrypt` |
| 輸入不存在、輸出已存在、讀寫失敗、缺 cryptography | `input_missing`、`output_exists`、`io_error`、`dependency_missing` | |

## 4. 換鎖（rewrap）與換檔案金鑰（rekey）的誠實限制

- `rewrap`：用任一把能開的鑰匙取出 file key，用新的收件人集合重建標頭（新 MAC），**內容位元組原封不動**
  （測試證明：新檔標頭之後的位元組與舊檔完全相同、舊鑰匙打不開新檔、新鑰匙與保留的萬用鎖可以）。
  預設會先把內容完整驗證一遍（不輸出明文），損壞的檔案不會被換鎖。
- **限制**：file key 沒有換。任何保留了**舊檔副本**的人，用舊鑰匙仍然打得開（測試也證明了這一點）；
  曾經解開過的人如果記下了 file key，也能解新檔。要真正讓舊鑰匙失效，請用 `rekey`，並刪掉舊副本。
- 因此 `rewrap` 不允許「從金鑰收件人改成密語」：舊收件人知道 file key，可以做出一個用這個密語就能解開的不同檔案，
  破壞密語檔「只有知道密語的人做得出來」的預期。只允許「密語換密語」；其他情況請用 `rekey`。
- `rekey`：解開後用新的 file key 與 nonce 整份重新加密（明文不落地），之後只有新收件人打得開新檔；已流出的舊副本不受影響。
- age 規格要求 file key 不得在多個檔案間重複使用；`rewrap` 產生的是「同一個檔案換了標頭」，請把舊檔視為同一份檔案的舊版本。

## 5. 測試向量與授權

- C2SP CCTV（<https://github.com/C2SP/CCTV>）`age/testdata`，commit `b88c4b2`（2026-11-01）。授權為 0BSD／CC0 1.0／Unlicense 任選，
  允許不附出處散布；本 repo 選 0BSD，出處與授權全文放在 `tests/data/age/PROVENANCE.md`。
- 147 個向量中放進 repo 的是 128 個（排除 19 個後量子 `hybrid*` 向量，本工具不支援）。全部 128 個都通過：
  預期結果（成功／不符／MAC 失敗／標頭失敗／內容失敗／armor 失敗）一致，成功與內容失敗的向量也比對「已釋出明文」的 SHA-256。
  另外還驗證：標頭重新序列化與原檔逐位元組相同、成功向量的內容用同一把金鑰重新加密得到相同密文、armor 重新編碼相同。
- 向量檔逐位元組保留：`tests/data/age/.gitattributes` 關掉換行轉換，測試先比對 `SHA256SUMS`。
- 設定環境變數 `ENCRYPTER_CCTV_AGE_DIR` 指到另外下載的 CCTV 資料時，會再跑一次完整的外部資料（後量子向量自動略過並統計）。
- 其他公開向量：BIP-173（Bech32）、RFC 7914（scrypt）、RFC 5869（HKDF），以及 age 規格裡的範例金鑰對。

跑法（在 repo 根目錄）：

```text
python -m unittest discover -s tools\encrypter\tests -p "test_age_*.py" -v
```

## 6. 已知的取捨

- 串流記憶體：加密最多保留兩個分塊、解密一個分塊；55 MiB 測試的峰值約 0.5 MiB，與 2 MiB 時相同。
- armor 解碼用 Python 處理，速度約數十 MB/s，適合文字傳遞的小檔；大檔建議用二進位。
- 自動辨識 armor 只看開頭（略過最多 1024 位元組空白後是否為 `-----`）；開頭有其他雜訊的檔案會被當成「不是 age 檔」。
