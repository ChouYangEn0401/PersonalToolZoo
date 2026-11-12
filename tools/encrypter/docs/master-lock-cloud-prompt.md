# 實作用 prompt：Encrypter「萬用鎖」金鑰槽格式（給雲端 Claude Code）

> 這份可以整段貼給雲端的 Claude Code session。內容自給自足：規格、測試要求、驗收條件都在下面。
> 背景說明與設計理由在同目錄的 `master-lock-research.md`（若該檔已在你的分支上，可以讀；沒有也能照本 prompt 完成）。

---

## 任務

在 PersonalToolZoo repo 的 Encrypter 工具（`tools/encrypter/`）中，實作一個新的加密檔格式「萬用鎖」（`.mlk`）：
每個檔案用一把隨機資料金鑰（DEK）加密內容，DEK 再分別包進多個「槽」——**萬用鎖槽**（X25519 公鑰，HPKE）、
**本次金鑰槽**（32 bytes 隨機金鑰）、**密語槽**（scrypt）。任何一個槽能開就能解密。
要支援：建立、解密、檢視、加槽、移除槽、換槽（只重包 DEK、不動內容）、rekey（換 DEK 並重新加密內容）。

**只用標準原語，不自創密碼學。** 規格以下文為準；有任何你認為規格不安全或無法實作的地方，停下來在回報裡說明，不要自行改規格。

## 硬規則

1. 從 `dev/encrypter`（若不存在就從 `master`）切新分支 `feat/encrypter-master-lock`，所有 commit 都在這條分支上。
   不合併到其他分支、不打 tag。
2. 先讀 repo 根目錄的 `AGENTS.md` 與 `CLAUDE.md`、`tools/encrypter/README.md`，遵守其中的規則
   （依賴要有主版本上限、`.bat` 只寫 ASCII、執行時資料不寫使用者資料夾等）。
3. **不要改變既有加密模式的行為**（`.isd`、All-In-One、Layered、PGP 系列）。新功能放新檔案；
   既有檔案只允許為了「掛上新功能」做最小的修改（例如在 CLI／GUI 註冊新指令或新分頁）。
4. 依賴：使用 Encrypter 已有的 **PyCryptodome**，把 `tools/encrypter/requirements.txt` 的版本改成 `pycryptodome>=3.22,<4`
   （3.22 起有 `Crypto.Protocol.HPKE`）。不要新增其他執行時依賴。測試可以額外用 `pytest`（開發用，不寫進 requirements）。
5. 一個 commit 一件事；標題英文 `type(scope): summary`（scope 用 `encrypter`），內文用繁體中文寫 What／Why 與怎麼驗證；
   用明確路徑 `git add`，不要 `git add -A`。結束時 `git status` 必須乾淨。
6. 不要寫入任何個人資訊、真實金鑰或 `.env`；所有測試金鑰在測試中產生；測試全部離線，不開網路埠。
7. 文件與回報用繁體中文（台灣用語）。

## 檔案配置

| 路徑 | 內容 |
|---|---|
| `tools/encrypter/crypto_tool/core/mlock.py` | 格式與操作的核心（串流讀寫） |
| `tools/encrypter/crypto_tool/core/mlock_cli.py` | 命令列介面（`python -m crypto_tool.core.mlock_cli ...`，在 `tools/encrypter` 底下執行） |
| `tools/encrypter/tests/test_mlock.py` | 單元測試 |
| `tools/encrypter/tests/test_mlock_cli.py` | CLI 測試 |
| `tools/encrypter/README.md` | 在「交接」段落加一小節：萬用鎖是什麼、指令、測試怎麼跑、限制 |

（若 `tools/encrypter/prototype/master_lock/` 存在，那是用 `cryptography` 寫的參考原型與測試，可以參考，但以本 prompt 的規格為準。）

## 格式規格 v1

所有整數 big-endian；字串常數是 ASCII、沒有結尾 NUL；`‖` 表示串接。

### 檔頭

```
檔案 = 檔頭 ‖ 內容
檔頭 = core(41) ‖ generation(u32) ‖ slot_count(u8) ‖ slot × slot_count ‖ header_mac(32)
core = magic(6) ‖ format_version(u8) ‖ suite(u8) ‖ chunk_log2(u8) ‖ file_id(32)
```

| 位移 | 長度 | 欄位 | 規則 |
|---|---|---|---|
| 0 | 6 | magic | `4d 4c 4f 43 4b 00`；不符 → E01 |
| 6 | 1 | format_version | 必須是 1；否則 E02 |
| 7 | 1 | suite | 必須是 1；否則 E03（不可自動退回其他演算法） |
| 8 | 1 | chunk_log2 | 12～20，預設 16；超出 → E04 |
| 9 | 32 | file_id | 隨機；rekey 時換新 |
| 41 | 4 | generation | encrypt 時 0；每次加槽／移除槽／換槽／rekey 加一 |
| 45 | 1 | slot_count | 1～16；0 → E04；> 16 → E10 |
| 46 | … | slots | 每個 `type(u8) ‖ body_len(u16) ‖ body`，body ≤ 1024 bytes；截斷或超長 → E04 |
| … | 32 | header_mac | 見下 |

DEK 為 32 bytes 隨機。包好的 DEK 一律是 48 bytes（32＋16 GCM 標籤）。

### 槽（已知型別的 body 長度必須完全相符，否則 E04）

- **`0x01` 萬用鎖**：`key_id(8) ‖ enc(32) ‖ ct(48)`，共 88 bytes。
  HPKE base mode（RFC 9180），KEM＝DHKEM(X25519, HKDF-SHA256)（0x0020）、KDF＝HKDF-SHA256（0x0001）、AEAD＝AES-256-GCM（0x0002）。
  `info = "mlock/v1/slot/hpke" ‖ core ‖ key_id`，AAD 為空，明文＝DEK。
  `key_id = SHA-256("mlock/v1/key-id" ‖ file_id ‖ X25519 公鑰 32 bytes)[:8]`。
  開槽時先比對 `key_id`，不符就跳過。
- **`0x02` 密語**：`salt(16) ‖ log_n(1) ‖ r(1) ‖ p(1) ‖ nonce(12) ‖ ct(48)`，共 79 bytes。
  `KEK = scrypt(密語經 Unicode NFC 正規化後的 UTF-8, salt, N=2^log_n, r, p, dkLen=32)`；
  `ct = AES-256-GCM(KEK, nonce, DEK, aad = "mlock/v1/slot/scrypt" ‖ core ‖ salt ‖ log_n ‖ r ‖ p)`。
  只接受 log_n 15～20、r＝8、p＝1，否則 E09（解密時也檢查，先檢查再算 scrypt）。建立時預設 log_n＝17。空密語 → E14。
- **`0x03` 本次金鑰**：`key_id(8) ‖ nonce(12) ‖ ct(48)`，共 68 bytes。
  `KEK = HKDF-SHA256(ikm=本次金鑰 32 bytes, salt=file_id, info="mlock/v1/slot/key", L=32)`；
  `ct = AES-256-GCM(KEK, nonce, DEK, aad = "mlock/v1/slot/key" ‖ core ‖ key_id)`；
  `key_id = HMAC-SHA256(key=本次金鑰, msg="mlock/v1/key-id" ‖ file_id)[:8]`。
- **`0x04`**：保留給 gpg 包 DEK（本任務不實作）。
- **其他型別**：解析時保留原樣、不解讀；換槽時原樣保留；仍在檔頭 MAC 範圍內。

### 檔頭 MAC

```
mac_key    = HKDF-SHA256(ikm=DEK, salt=file_id, info="mlock/v1/header", L=32)
header_mac = HMAC-SHA256(mac_key, 檔頭從位移 0 到最後一個槽結尾的位元組)
```

用固定時間比較。槽打開後 MAC 不符 → E06。

### 內容

```
payload_key = HKDF-SHA256(ikm=DEK, salt=file_id, info="mlock/v1/payload", L=32)
明文切成 2^chunk_log2 bytes 的塊；最後一塊可較短；只有明文為空時最後一塊才可以是空的。
nonce_i = uint88_be(i) ‖ (0x01 若是最後一塊，否則 0x00)          # 12 bytes
ct_i    = AES-256-GCM(payload_key, nonce_i, chunk_i, aad = core)  # 每塊多 16 bytes
```

解密規則：

1. 嚴格解析檔頭（不需金鑰）→ 依序用使用者提供的每把鑰匙試每個相同型別的槽 → 取得 DEK → **先驗證檔頭 MAC** → 才處理內容。
   全部打不開 → E05。
2. 非最後一塊必須正好 `2^chunk_log2 + 16` bytes；最後一塊 16～`2^chunk_log2 + 16` bytes；有資料時最後一塊不可只有 16 bytes（E07）。
   內容長度小於 16 → E08。
3. 最後一塊用旗標 0x01 解不開、但用 0x00 解得開 → E08（在區塊邊界被截斷）；其他區塊失敗 → E07。
4. **失敗時不得輸出任何明文**：寫入暫存檔（同目錄），全部成功才原子替換成目標檔；失敗就刪除暫存檔。
5. 串流處理：記憶體用量不隨檔案大小成長。

### 操作

| 操作 | DEK | file_id | generation | 槽 | 內容 |
|---|---|---|---|---|---|
| encrypt | 新 | 新 | 0 | 新建 | 加密 |
| add_slot／remove_slot／replace_slot | 不變 | 不變 | +1 | 改 | 原封不動複製 |
| rekey | 新 | 新 | +1 | 全部重建 | 重新加密 |

保護規則：

- encrypt 與 rekey 預設**必須**至少有一個萬用鎖槽，否則 E13（提供 `require_master=False` 讓測試或進階使用者關掉）。
- 不能移除最後一個槽（E11）。移除或換掉**唯一的**萬用鎖槽要明確的 `allow_remove_master=True`，否則 E12
  （換成另一個萬用鎖則允許）。
- 槽數上限 16（E10）。

### 萬用鎖私鑰檔

```
IDENTITY = "MLOCKID\0"(8) ‖ version=1(u8) ‖ log_n(u8) ‖ r(u8) ‖ p(u8) ‖ salt(16) ‖ nonce(12) ‖ ct(48)
KEK = scrypt(NFC UTF-8 密語, salt, 2^log_n, r, p, 32)
ct  = AES-256-GCM(KEK, nonce, X25519 私鑰 32 bytes, aad = "mlock/v1/identity" ‖ 前 28 bytes)
```

格式錯、密語錯、被改 → E15；scrypt 參數超出範圍 → E09。

### 錯誤代碼（穩定，不可改號）

| 代碼 | 名稱 | 補救建議（顯示給使用者） |
|---|---|---|
| MLK-E01 | NOT_MLOCK | 這不是萬用鎖格式的檔案，確認選對檔案 |
| MLK-E02 | UNSUPPORTED_VERSION | 格式版本未知，請用支援該版本的程式 |
| MLK-E03 | UNSUPPORTED_SUITE | 演算法組合未知或停用；不會自動改用其他演算法 |
| MLK-E04 | MALFORMED_HEADER | 檔頭損毀或被截斷，從備份取回 |
| MLK-E05 | NO_MATCHING_SLOT | 金鑰錯、已被換掉，或該槽被竄改；改用萬用鎖試試 |
| MLK-E06 | HEADER_TAMPERED | 檔頭被改過，不要信任這份檔案 |
| MLK-E07 | PAYLOAD_TAMPERED | 內容被改過或損毀，沒有輸出任何明文 |
| MLK-E08 | TRUNCATED | 檔案不完整，重新下載 |
| MLK-E09 | KDF_PARAMS_OUT_OF_RANGE | scrypt 參數太弱或太大，用萬用鎖開啟後重建該槽 |
| MLK-E10 | TOO_MANY_SLOTS | 超過 16 個槽，先移除不用的 |
| MLK-E11 | LAST_SLOT | 不能移除最後一個槽 |
| MLK-E12 | MASTER_SLOT_PROTECTED | 會移除唯一的萬用鎖槽，需要明確確認 |
| MLK-E13 | NO_MASTER_SLOT | 新檔案必須有萬用鎖槽 |
| MLK-E14 | BAD_ARGUMENT | 參數不正確 |
| MLK-E15 | BAD_IDENTITY_FILE | 私鑰檔損毀或密語錯，改用另一份備份 |

例外類別帶 `code`、`name`、`hint` 屬性。**任何錯誤訊息、log、`repr` 都不可以包含金鑰、密語、DEK 或明文。**

## 已知答案向量（實作必須逐位元組相同）

- 亂數來源（只在測試中注入；正式程式用作業系統亂數）：每次需要 n bytes 時，從目前的 counter 開始依序計算
  `SHA-256("mlock-v1-kat" ‖ uint64_be(counter))`（每算一次 counter 加一）並串接，取前 n bytes，剩下的丟掉。counter 從 0 起。
- 亂數取用順序：DEK(32)、file_id(32)、本次金鑰槽 nonce(12)、密語槽 salt(16)、密語槽 nonce(12)。
- 槽依序：本次金鑰＝`000102…1f`（32 bytes）、密語＝`"kat passphrase"`（log_n＝15、r＝8、p＝1）。不含萬用鎖槽、`require_master=False`。
- chunk_log2＝12；明文＝bytes 0x00～0xff 重複 16 次，再接 `"tail"`（共 4100 bytes）。

預期：

```
DEK          = 3936b60626bc7d3378f274806bdd1c5ab2255429f9c13dd7fd016ec2dcbcc100
檔頭（231 bytes，十六進位，連續）=
4d4c4f434b0001010cae302a952451863a177a08f1c616c365d0f88c88e25e5c3cefa911f04d88186a0000000002030044
1b5ecb6b38831ddd214adc37e7b9c07e9e7d160c5ca4af1d47984fa7b94c0c5a3b46882fbfb184dfe965c4934a16e968
3f6c253dd49651c64dd4b09d7aa45a025a28d71f02004f114d4d8ae1f800a427074f6dc55c29820f0801f230d6876883
e50d66e71fdb2e23feda01aef2f68a0acdafa844010c7313125585299a769d21b93b7fd41409172a2ff310ed8a9dc15e
23c953edeed14c2766e5d02bc6fc45efca781c581b6206bf5b67d5f988ee22779ec3bd1a8a47
整個檔案的 SHA-256 = c935cf3d42a93c8baec2028d322acab2d8a50e078dd6aa51fb21d1a5f65cff09
```

（上面的檔頭只是為了閱讀而換行，實際是連續的 462 個十六進位字元。）

## 命令列介面

祕密不可從命令列參數讀：密語用終端機提示（`getpass`）或 `--passphrase-file`；金鑰從檔案讀。
所有寫入先寫暫存檔再原子替換；沒有 `--in-place` 時必須給 `-o`，且不覆蓋已存在的檔案（除非 `--force`）。

| 指令 | 用途 |
|---|---|
| `keygen --identity F --pub F` | 產生萬用鎖，私鑰以密語封存；印出公鑰指紋（SHA-256 前 16 個十六進位字元） |
| `session-keygen F` | 產生 32 bytes 本次金鑰檔 |
| `encrypt IN -o OUT --master PUB [--session F]... [--passphrase]` | 建立 |
| `decrypt IN -o OUT (--identity F | --session F | --passphrase)` | 解密 |
| `inspect IN [--verify-with ...] [--json]` | 版本、塊大小、槽清單（型別、key_id、scrypt log_n）、generation、file_id、fingerprint（整個檔頭的 SHA-256）、明文長度 |
| `add-slot IN --with ... (新槽參數)` | 加槽 |
| `remove-slot IN --with ... --slot N [--allow-remove-master]` | 移除槽 |
| `replace-slot IN --with ... (--slot N | --old-session F) (新槽參數)` | 換槽 |
| `rekey IN --with ... --master PUB [新槽參數]` | 換 DEK 並重新加密 |
| `check-revoked IN --old-session F` | 舊本次金鑰打不開才回 0；打得開回非 0 並警告 |

結束碼：0 成功、2 用法錯誤、10＋代碼數字（例如 E05 → 15）。`--json` 時錯誤輸出 `{"code","name","hint"}`。

## 測試要求（pytest，全部離線，金鑰在測試中產生）

1. **已知答案**：RFC 7914 scrypt 向量（`"password"`／`"NaCl"`／N＝1024／r＝8／p＝16，前 32 bytes 為
   `fdbabe1c9d3472007856e7190d01e9fe7c6ad7cbc8237830e77376634b373162`）；RFC 5869 HKDF 測試案例 1；上面的格式向量；
   再寫一個測試**只用規格與原語**（不呼叫你的模組內部函式）手動解開格式向量。
2. **往返**：三種槽各自能開；明文長度 0、1、塊大小−1、塊大小、塊大小＋1、多塊；預設塊大小；大檔（例如 5 MB）以串流處理。
3. **錯金鑰**：別的萬用鎖、別的本次金鑰、錯密語 → E05；沒給金鑰 → E14。
4. **竄改**：檔頭**每一個位元組**翻轉都必須失敗（對萬用鎖與本次金鑰各試一次）；內容抽樣翻轉 → E07；
   區塊對調 → E07；把別的檔案的整段檔頭或單一槽移植過來 → 失敗。
5. **截斷／附加**：截在區塊邊界 → E08；截在塊中間 → E07；只剩檔頭 → E08；檔頭被截 → E04；附加資料 → 失敗。
6. **降級**：版本、suite 改值 → E02／E03；密語槽 log_n 改成低於 15 → E09、改成範圍內其他值 → E05；chunk_log2 改值 → 失敗。
7. **換槽**：換掉本次金鑰槽後，舊本次金鑰 → E05、新本次金鑰與萬用鎖可開；內容位元組完全相同；generation＋1；fingerprint 改變。
8. **誠實的限制**（測試要寫出來，名稱與註解說明這是限制而不是 bug）：換槽前的舊檔用舊本次金鑰仍打得開；
   用舊槽取得的 DEK 在換槽後仍能解內容，rekey 後不行。
9. **rekey**：舊本次金鑰 → E05；萬用鎖與新本次金鑰可開；file_id 改變。
10. **保護規則**：E10、E11、E12、E13；萬用鎖換成新萬用鎖可行。
11. **祕密不外洩**：輸出檔不含 DEK、本次金鑰、密語、萬用鎖私鑰、明文片段；`repr`、例外訊息、`inspect` 輸出、CLI 的 stdout／stderr 都不含祕密。
12. **失敗不留明文**：解密失敗後目標檔不存在、暫存檔已刪除。
13. **私鑰檔**：往返；錯密語 → E15；每個位元組翻轉都失敗。
14. **CLI**：每個指令至少一個成功案例與一個失敗案例（檢查結束碼與 `--json` 輸出）；密語從 `--passphrase-file` 讀。
15. 既有的 Encrypter 測試全部仍然通過。

## 驗收與回報

- `cd tools/encrypter` 後跑 pytest，全部通過；回報測試數量與執行時間。
- 若 PyCryptodome 的 HPKE 無法指定上面的 KEM／KDF／AEAD 組合、或無法傳入 `info`，**停下來回報**，不要換成別的組合。
- 回報內容：結論、做了哪些 commit（hash＋標題）、測試結果、與規格不同或沒做到的地方、需要人決定的事。

## 不要做的事

- 不要修改或移除既有的 `.isd` 格式與模式；不要自動轉換或刪除使用者的舊檔案。
- 不要自己設計新的密碼學構造、不要改常數字串、不要改錯誤代碼編號。
- 不要把祕密寫進 log、例外訊息、暫存檔名或命令列參數。
- 不要新增 GUI（另一個工作包），不要改打包設定，不要發版、不要打 tag、不要合併分支。
- 不要寫入任何個人資訊或真實金鑰。
