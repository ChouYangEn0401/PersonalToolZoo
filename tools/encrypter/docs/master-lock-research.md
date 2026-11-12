# 萬用鎖＋本次金鑰：研究、設計與原型

> **已落地（2026-11-13，Encrypter 0.4.0）：萬用鎖用 age／OpenPGP 的標準多收件人實作，加上 `rewrap`（換鎖）與 `rekey`（換檔案金鑰）；**
> **下面的 MLOCK 自有格式原型保留為研究參考，不打包、不被工具匯入，也不會產生使用者的檔案。**
> 用法見工具 README「萬用鎖」；格式決定見 `handoffs/20261113-013906-format-decision-age-openpgp.md`。
>
> 狀態（研究當時）：研究完成、原型可跑、尚未進入 Encrypter 正式功能。
> 原型：[`../prototype/master_lock/`](../prototype/master_lock/)（`mlock.py` ＋ `test_mlock.py`）。
> 給雲端實作用的 prompt：[`master-lock-cloud-prompt.md`](master-lock-cloud-prompt.md)。

## 0. 結論先講

| 問題 | 答案 |
|---|---|
| 這個想法對嗎？ | **方向對。** 「一把永遠留著的萬用鎖＋每次可換的本次金鑰」就是密碼學裡標準的**信封加密＋多個金鑰槽**（age 多收件人、OpenPGP 多收件人、LUKS 金鑰槽、SOPS、雲端 KMS 都是這樣做）。 |
| 哪裡要修正？ | ① **不要用層層巢狀加密做**：巢狀是「每一層的鑰匙都要有」（且），萬用鎖要的是「任何一把都能開」（或），巢狀在結構上就做不到。② 安全**不能**靠「別人不知道內層長怎樣」，只能靠金鑰。③ **換本次金鑰不會讓已經被複製走的舊檔案失效**，也收不回對方已經看過的內容。④ 萬用鎖變成「一把開全部」，它外洩就全部外洩，保管方式才是整個設計的重點。 |
| 推薦做法（一句話） | **每個檔案一把隨機資料金鑰（DEK）加密內容，再把 DEK 分別包進「萬用鎖槽（公鑰，私鑰離線保管）」和「本次金鑰槽」；換本次金鑰時，對方沒解開過就只重包槽（快），對方解開過就換 DEK 整份重新加密（rekey）。** |
| 原型 | `prototype/master_lock/mlock.py`，44 個測試全過（含已知答案、竄改、截斷、降級、換槽後舊本次金鑰失效且萬用鎖仍可、祕密不外洩）。 |
| 要你決定的事 | 見 [§12](#12-需要擁有者決定的事)，共 8 項，每項都有建議與預設。 |

---

## 1. 白話說明：哪裡對、哪裡要修正

### 1.1 對的部分

- **萬用鎖永遠留著**：每個檔案都多放一個「萬用鎖能開」的槽，擁有者只用萬用鎖就能取回。這正是 LUKS 的「多個金鑰槽」、
  OpenPGP 的「每個收件人一個 PKESK 封包」、age 的「每個收件人一個 stanza」、SOPS 的「每個 master key 各包一份 data key」。
- **本次金鑰可以換**：只要「重包槽」（rewrap）就能換，不必重新加密整份內容（同 LUKS `luksKeyAdd`＋`luksKillSlot`、SOPS `updatekeys`）。
- **雲端／別人只拿到密文**：沒有任何一把鑰匙的人什麼都打不開。

### 1.2 需要修正的部分

1. **「或」不是「且」**。層層巢狀＝箱子裡放箱子，每個箱子一把鎖，要依序打開每一把才拿得到東西。
   想用巢狀做萬用鎖只有兩種擺法，兩種都不行：
   - 萬用鎖在外層：拿本次金鑰的人連外層都打不開。
   - 萬用鎖在內層：擁有者還是需要本次金鑰才能打開外層，萬用鎖不再「萬用」。
   要「任何一把都能開同一個箱子」，正確做法是**同一把資料金鑰被包好幾份**，每一份對應一把鑰匙（金鑰槽）。
2. **不要靠「別人不知道內層」**。設計要假設格式是公開的（Kerckhoffs 原則），強度只來自金鑰。
   多包幾層只有在你**刻意要求「兩把鑰匙都要有」**（例如兩人同意才能開）時才有意義，那是另一個功能。
3. **換本次金鑰的極限**（必須誠實）：
   - 換槽只改「新的那份檔案」。對方或雲端**已經複製走的舊檔案**，用舊本次金鑰照樣打得開。
   - 對方只要解開過一次，就可能留著**明文**或**資料金鑰（DEK）**。換槽擋不住留著 DEK 的人（內容沒變）；要換 DEK
     並整份重新加密（rekey）才擋得住；**明文擋不住**，這是任何加密都做不到的（沒有真正的 DRM）。
   - 所以「交給別人短期使用」的正確收尾是：**rekey ＋ 刪掉雲端上的舊版本（含版本紀錄）**，並接受對方可能留有內容。
4. **萬用鎖是單點失效**。它外洩＝所有加過萬用鎖槽的檔案（包括散落各處的舊副本）全部外洩；它遺失＝只靠它的檔案永遠打不開。
   因此建議萬用鎖用**公鑰型**：日常加密只需要公鑰，私鑰可以一直離線（見 [§9](#9-萬用鎖怎麼保管)）。
5. **槽的持有人跟擁有者一樣強**（在那份檔案上）。拿到本次金鑰的人能解出 DEK，因此也能改內容、加減槽、重算檔頭驗證碼。
   格式擋得住**外人**竄改，擋不住**槽持有人**竄改；要能證明「這份是我做的、沒被改過」需要另外加簽章（工作包 WP7）。

---

## 2. 對照公開做法

「已查證」＝本次讀過該網址的原文或官方摘要；「推測」＝依既有知識，本次沒有讀到原文確認。

| 系統 | 怎麼做「多把鑰匙都能開」 | 換鑰匙要不要重加密內容 | 跟本設計的關係 | 查證 |
|---|---|---|---|---|
| **age** | 每檔一把隨機 file key（16 bytes），每個收件人一個 stanza 包它；檔頭用 file key 衍生的 HMAC 驗證；內容 64 KiB 分塊 ChaCha20-Poly1305，nonce＝11 bytes 計數器＋最後一塊旗標 | 規格沒有換槽操作（推測：要重新加密） | 本設計的分塊與 nonce 規則、檔頭 MAC 直接沿用 age 的做法 | 已查證（規格）；「age 沒有換槽指令」為推測 |
| age 的密語（scrypt）stanza | 規格要求 scrypt stanza **不能跟其他 stanza 混用**，理由是「維持密語加密隱含的驗證期待」 | — | 本設計**刻意允許**混用（萬用鎖＋密語），代價是密語檔不代表「只有知道密語的人做的」，見 §1.2 第 5 點 | 已查證 |
| **OpenPGP（RFC 9580）** | 一把 session key；每個公鑰收件人一個 PKESK、每個密碼一個 SKESK，任一個能解即可 | session key 不變時理論上可只重包（推測：gpg 的 `--show-session-key`／`--override-session-key` 可手動做到，本次未查證） | §8 的 gpg 互通 | 多收件人、SKESK、SEIPD v2（HKDF＋salt、分塊、最後的驗證標籤）已查證 |
| GnuPG `--throw-keyids` | 不在密文裡放收件人 key ID，降低流量分析；代價是解密要逐把試 | — | 說明「槽會洩漏收件人身分」這個問題是真的 | 已查證 |
| **LUKS（cryptsetup）** | 隨機 master key，每個 key slot 用一組密語包一份（LUKS1 有 8 個槽） | 換密語**不**換 master key；換 master key 要「完整備份、重新格式化、還原」 | 本設計的 rewrap／rekey 就是這兩種操作 | 已查證（FAQ 2.4、3.4、6.10、6.15） |
| LUKS 的檔頭備份 | FAQ 6.7：改掉或停用某個槽後，**舊的二進位備份仍保有舊槽**，舊密語還是能開備份 | — | 正是 §1.2 第 3 點「舊副本不會失效」的同一件事 | 已查證 |
| **SOPS** | 一把 data key 加密所有值；每個 master key（PGP、age、KMS…）各包一份 | `updatekeys` 只改誰能開（不換 data key）；`rotate` 產生新 data key 並重新加密所有值 | 對應 rewrap／rekey | 已查證 |
| SOPS 移除外洩金鑰的順序 | 先 `updatekeys` 移除金鑰，再 `rotate`；順序反了「被外洩的金鑰在某些情況下仍能存取資料」 | — | §7 的輪替流程照這個順序 | 已查證 |
| **Google Cloud KMS** | 信封加密：DEK 加密資料，KEK（在 KMS 內）包 DEK；建議每次寫入用新的 DEK、不要存明文 DEK | 輪替 KEK「不會」重新加密既有資料，要自己重加密；舊版本金鑰仍用來解舊資料 | 支持「每檔一把新 DEK」與「輪替≠舊資料失效」 | 已查證 |
| **AWS KMS** | 同為信封加密；說明可「只重新加密 data key，而不必用不同金鑰重複加密原始資料」 | 輪替 KMS key 不影響已保護的資料，也「不會緩解 data key 外洩的影響」；舊 key material 會保留 | 同上；也說明「DEK 外洩後只換外層沒用」 | 已查證 |
| **HPKE（RFC 9180）** | 對一把公鑰加密任意資料的標準組合（KEM＋KDF＋AEAD）；有 base／psk／auth 模式 | — | 本設計的萬用鎖槽＝HPKE base mode 包 DEK | 已查證；RFC 也說明 HPKE 對收件人私鑰外洩**沒有**前向保密、不隱藏長度、不規定傳輸格式 |
| `cryptography`（Python）HPKE | 本機 50.0.2 有 `hazmat.primitives.hpke.Suite`（X25519／HKDF-SHA256／AES-256-GCM，single-shot，參數 `info`） | — | 原型使用 | 已在本機確認 API |
| PyCryptodome HPKE | `Crypto.Protocol.HPKE`：支援 X25519、AES256_GCM、`info`、`enc` 屬性 | — | 落地到 Encrypter 時可不新增依賴（Encrypter 已用 PyCryptodome） | API 已查證；「3.22.0 加入」來自轉載版本紀錄的網站；與 `cryptography` 的 HPKE 互通**未測**（推測可互通，因同為 RFC 9180） |

### 2.1 本機現有 Encrypter 的對照（讀程式碼得到，非推測）

| 現有功能 | 它是什麼 | 能不能當萬用鎖 | 其他問題 |
|---|---|---|---|
| Mixture「All-In-One」（README 舊稱 Layered） | 同一份資料連續加密 N 次，包成一個 `.isd` | 不能：每一段的密碼都要有（且） | `NOTE` 是明文 JSON、沒被驗證：會洩漏原始檔名、演算法鏈、作者、密碼提示，也可被改 |
| Mixture「Layered」（README 舊稱 Nested） | 每段都包成完整 `.isd`，一層包一層 | 不能（同上）；換外層＝整份重加密 | 同上；每層都多一次 base64（約 +33%） |
| 預設演算法 AES-256-CBC | 沒有 MAC 的 CBC | — | 密文可被改而不被發現（可塑性）；`XOR`／`XOR-FOLD`／`Base64` 不是安全加密 |
| **PGP-Escrow／PGP-Multi** | RSA-OAEP 包同一把 AES-GCM 金鑰給多個收件人 | **最接近**：已經是「或」的結構 | 收件人清單不在 AEAD 的驗證範圍內；整檔放記憶體、不分塊；沒有換槽；RSA-4096 產鑰慢 |

> 命名提醒：`crypto_tool/README.md`／`tools/encrypter/README.md` 仍用舊名（Layered＝融合、Nested＝逐層），
> 程式（v1.4 起）已改成 All-In-One＝融合、Layered＝逐層。兩份說明對不上，容易誤會。

**結論：** 萬用鎖不是「把現有 Layered／Nested 修好」，而是**換一個結構**：PGP-Escrow 的「或」，加上嚴格的檔頭驗證、分塊、可換槽、對稱的本次金鑰槽。

---

## 3. 為什麼不要層層巢狀加密

| 面向 | 巢狀加密（外層包內層） | 一把 DEK＋多個槽 |
|---|---|---|
| 鑰匙關係 | 且：每層都要 | 或：任一槽即可（要「且」另用門檻分持） |
| 萬用鎖單獨開檔 | 做不到（見 §1.2） | 做得到 |
| 換本次金鑰 | 解開外層、重新加密整份（O(檔案大小)） | 重包一個 48 bytes 的 DEK（O(1)）；需要時才 rekey |
| 效能 | 每層都完整讀寫一次；`.isd` 每層再 base64 一次 | 內容只加密一次；每 64 KiB 只多 16 bytes |
| 安全增益 | 單一 AEAD 已足夠時，多層不會更安全；反而更多金鑰要管 | 安全只來自 AEAD 與金鑰 |
| 中繼資料 | 每層一份明文 NOTE（層數、演算法、檔名…） | 只有固定格式的檔頭（槽數、型別、大小） |
| 竄改偵測 | 取決於每層演算法；CBC 層沒有 | 檔頭 HMAC＋每塊 GCM 標籤，全部驗證 |
| 錯誤處理 | 錯在第幾層難以判斷 | 穩定錯誤代碼（§6.2） |
| 程式複雜度 | 每層都要記住演算法與金鑰順序 | 一個固定流程 |

---

## 4. 威脅模型

| # | 情境 | 結果 | 對策／限制 |
|---|---|---|---|
| T1 | 雲端業者或偷看雲端的人，只有密文 | 讀不到內容 | 看得到：檔案大小（≈明文大小）、槽數與槽型別、密語槽的 scrypt 參數、`file_id`、`generation`、各槽 `key_id`、上傳／修改時間。要隱藏大小需要補齊（v1 不做） |
| T2 | 本次金鑰外洩，但沒人用過 | 拿到的人＋任何一份檔案副本＝能開 | 立刻換槽（rewrap）＋刪除雲端所有舊版本；已被複製走的舊副本收不回 |
| T3 | 本次金鑰的持有人用完後 | 可能留有明文、DEK、舊檔 | **rekey**（換 DEK）擋住「留 DEK 開新檔」；明文與舊副本擋不住 |
| T4 | 萬用鎖私鑰外洩 | 所有有萬用鎖槽的檔案（含舊副本）全開 | 換新萬用鎖並對每個檔案 replace-slot（或 rekey）；舊副本仍危險 → 保管是重點（§9） |
| T5 | 萬用鎖私鑰遺失 | 只靠它的檔案永遠打不開 | 至少兩份離線備份＋一份紙本；建立新檔時程式**強制**要有萬用鎖槽 |
| T6 | 外人改檔頭（槽、世代、參數） | 被擋：`MLK-E05`／`MLK-E06` | 測試逐位元組翻轉檔頭，全部失敗 |
| T7 | 外人改內容、重排、截斷、附加 | 被擋：`MLK-E07`／`MLK-E08` | 最後一塊有旗標，截在區塊邊界也抓得到 |
| T8 | 降級（改版本、suite、scrypt 參數、chunk 大小） | 被擋：`MLK-E02`／`E03`／`E09`／`E05` | 程式只接受已知 suite，不自動退回；scrypt 參數在 AAD 內且有下限 |
| T9 | 回滾／重放：把雲端檔案換回舊版（含舊槽或舊內容） | **格式本身擋不住**（沒有外部狀態） | 自己記下最新版的 `fingerprint`／`generation`，用 `inspect` 比對；刪除雲端舊版本 |
| T10 | 槽持有人改內容或偽造檔案後交回 | 檔案仍可被萬用鎖打開且驗證通過 | 格式不提供來源證明；需要簽章（WP7）或自己保留雜湊 |
| T11 | 槽持有人移除萬用鎖槽或刪檔 | 那份檔案萬用鎖打不開 | 可用性靠自己的備份，不靠密碼學 |
| T12 | 電腦中毒時使用萬用鎖私鑰 | 私鑰與明文都可能被偷 | 公鑰型萬用鎖：日常加密不用私鑰；取回只在乾淨環境做，或用硬體金鑰（§8 gpg 槽） |
| T13 | 密語太弱 | 離線暴力破解 | scrypt 預設 2^17（128 MiB）；本次金鑰建議用**隨機金鑰檔**而非密語 |
| T14 | 加密時被換掉萬用鎖公鑰 | 萬用鎖打不開，或攻擊者能開 | 公鑰指紋人工核對一次並記在紙本；公鑰檔放唯讀位置 |
| T15 | 同一把本次金鑰用在很多檔案 | 雲端不能用 `key_id` 串連（每檔不同）；但金鑰外洩時全部受影響 | 一次分享一把新的本次金鑰 |

---

## 5. 檔案格式規格 v1

所有整數為 big-endian。所有字串常數為 ASCII，沒有結尾 NUL。

### 5.1 整體

```
檔案 = 檔頭 ‖ 內容
檔頭 = core(41) ‖ generation(u32) ‖ slot_count(u8) ‖ slot × slot_count ‖ header_mac(32)
core = magic(6) ‖ format_version(u8) ‖ suite(u8) ‖ chunk_log2(u8) ‖ file_id(32)
```

| 位移 | 長度 | 欄位 | 規則 |
|---|---|---|---|
| 0 | 6 | magic | `4d 4c 4f 43 4b 00`（"MLOCK\0"），不符→`MLK-E01` |
| 6 | 1 | format_version | `1`；其他→`MLK-E02` |
| 7 | 1 | suite | `1`；其他→`MLK-E03`（不自動退回其他演算法） |
| 8 | 1 | chunk_log2 | 12～20，預設 16（64 KiB）；超出→`MLK-E04` |
| 9 | 32 | file_id | 隨機；也是所有 HKDF 的 salt；rekey 時換新 |
| 41 | 4 | generation | 每次換槽／加槽／移除／rekey 加一 |
| 45 | 1 | slot_count | 1～16；0→`MLK-E04`，>16→`MLK-E10` |
| 46 | … | slots | 每個：`type(u8) ‖ body_len(u16) ‖ body`；body ≤ 1024 bytes |
| … | 32 | header_mac | 見 §5.3 |

`core`（前 41 bytes）在換槽時不變，是每個內容區塊的 AAD；所以**換槽不需要重新加密內容**。

### 5.2 槽

suite 1 的金鑰長度：DEK 32 bytes；所有包好的 DEK 都是 32＋16（GCM 標籤）＝48 bytes。

| type | 名稱 | body（長度固定，不符→`MLK-E04`） | 怎麼包 DEK |
|---|---|---|---|
| `0x01` | 萬用鎖（公鑰） | `key_id(8) ‖ enc(32) ‖ ct(48)`，共 88 | HPKE base mode（RFC 9180），KEM＝DHKEM(X25519, HKDF-SHA256)、KDF＝HKDF-SHA256、AEAD＝AES-256-GCM；`info = "mlock/v1/slot/hpke" ‖ core ‖ key_id`，`aad` 空；`key_id = SHA-256("mlock/v1/key-id" ‖ file_id ‖ 公鑰32)[:8]` |
| `0x02` | 密語 | `salt(16) ‖ log_n(1) ‖ r(1) ‖ p(1) ‖ nonce(12) ‖ ct(48)`，共 79 | `KEK = scrypt(NFC 正規化後的 UTF-8 密語, salt, N=2^log_n, r, p, 32)`；`ct = AES-256-GCM(KEK, nonce, DEK, aad = "mlock/v1/slot/scrypt" ‖ core ‖ salt ‖ log_n ‖ r ‖ p)`；接受 log_n 15～20、r＝8、p＝1，其餘→`MLK-E09`；建立時預設 log_n＝17 |
| `0x03` | 本次金鑰（32 bytes 隨機） | `key_id(8) ‖ nonce(12) ‖ ct(48)`，共 68 | `KEK = HKDF-SHA256(ikm=本次金鑰, salt=file_id, info="mlock/v1/slot/key", L=32)`；`ct = AES-256-GCM(KEK, nonce, DEK, aad = "mlock/v1/slot/key" ‖ core ‖ key_id)`；`key_id = HMAC-SHA256(本次金鑰, "mlock/v1/key-id" ‖ file_id)[:8]` |
| `0x04` | gpg（保留） | 一段 OpenPGP 訊息，內容是 DEK | 見 §8；原型不實作 |
| 其他 | 未知 | 任意 | 解析時保留原樣、不解讀；仍在檔頭 MAC 範圍內 |

設計說明：

- 所有槽都把 `core`（含 `file_id`）放進 AAD／info：把一個槽搬到別的檔案會打不開。
- `key_id` 讓程式不必每個槽都試；本次金鑰的 `key_id` 每個檔案都不同，雲端無法用它把不同檔案串在一起。
  萬用鎖的 `key_id` 任何知道公鑰的人都算得出來 → **萬用鎖公鑰不要公開張貼**。
- 每把 KEK 只包極少次（每檔每槽一次），隨機 96-bit nonce 不會碰到 GCM 的使用上限。

### 5.3 檔頭驗證碼

```
mac_key    = HKDF-SHA256(ikm=DEK, salt=file_id, info="mlock/v1/header", L=32)
header_mac = HMAC-SHA256(mac_key, 檔頭從位移 0 到最後一個槽結尾的所有位元組)
```

比對一律用固定時間比較。任何能開槽的人都能重算 MAC（§1.2 第 5 點）。

### 5.4 內容（分塊）

```
payload_key = HKDF-SHA256(ikm=DEK, salt=file_id, info="mlock/v1/payload", L=32)
明文切成 2^chunk_log2 bytes 的區塊；最後一塊可以較短；只有明文是空的時候最後一塊才可以是空的。
nonce_i     = uint88_be(i) ‖ (0x01 若為最後一塊，否則 0x00)        # 12 bytes，同 age
ct_i        = AES-256-GCM(payload_key, nonce_i, chunk_i, aad = core)  # 每塊 = 明文長度 + 16
```

解密規則：

1. 嚴格解析檔頭 → 找能開的槽 → 取得 DEK → **先驗證檔頭 MAC** 才碰內容。
2. 除了最後一塊，每塊都必須正好 `2^chunk_log2 + 16` bytes；最後一塊 16～`2^chunk_log2 + 16` bytes；有資料時最後一塊不可以只有 16 bytes。
3. 最後一塊必須用旗標 `0x01` 解得開。若用 `0x00` 解得開 → 檔案在區塊邊界被截斷（`MLK-E08`）。
4. 任何一塊失敗都不輸出任何明文。串流實作要寫到暫存檔、全部成功才改名（原子替換），失敗就刪暫存檔。

### 5.5 操作對格式的影響

| 操作 | DEK | file_id | generation | 槽 | 內容 |
|---|---|---|---|---|---|
| encrypt | 新 | 新 | 0 | 新建 | 加密 |
| add-slot／remove-slot／replace-slot（rewrap） | 不變 | 不變 | +1 | 改 | **原封不動** |
| rekey | 新 | 新 | +1 | 全部重建 | 重新加密 |

### 5.6 萬用鎖私鑰檔（離線備份用）

```
IDENTITY = "MLOCKID\0"(8) ‖ version=1(u8) ‖ log_n(u8) ‖ r(u8) ‖ p(u8) ‖ salt(16) ‖ nonce(12) ‖ ct(48)
KEK      = scrypt(NFC UTF-8 密語, salt, 2^log_n, r, p, 32)
ct       = AES-256-GCM(KEK, nonce, X25519 私鑰 32 bytes, aad = "mlock/v1/identity" ‖ 前 28 bytes)
```

錯誤一律回 `MLK-E15`（參數超出範圍則 `MLK-E09`）。

### 5.7 已知答案向量（實作必須產生完全相同的位元組）

輸入（不含萬用鎖槽，因為 HPKE 的暫時金鑰無法固定）：

- 亂數來源：`R(n)` 依序取 `SHA-256("mlock-v1-kat" ‖ uint64_be(counter))` 串接，counter 從 0 起、每算一次加一，取前 n bytes；每次呼叫重新從**新的** counter 開始（不沿用上次剩下的位元組）。
- 亂數取用順序：DEK(32)、file_id(32)、本次金鑰槽 nonce(12)、密語槽 salt(16)、密語槽 nonce(12)。
- 槽順序：本次金鑰＝`00 01 02 … 1f`（32 bytes）、密語＝`"kat passphrase"`（log_n＝15、r＝8、p＝1）。
- chunk_log2＝12；明文＝`bytes(0..255)` 重複 16 次 ‖ `"tail"`（4100 bytes → 兩塊）。

預期：

```
DEK        = 3936b60626bc7d3378f274806bdd1c5ab2255429f9c13dd7fd016ec2dcbcc100
檔頭(231B) = 4d4c4f434b0001010cae302a952451863a177a08f1c616c365d0f88c88e25e5c3cefa911f04d88186a
             0000000002
             030044 1b5ecb6b38831ddd 214adc37e7b9c07e9e7d160c
             5ca4af1d47984fa7b94c0c5a3b46882fbfb184dfe965c4934a16e9683f6c253dd49651c64dd4b09d7aa45a025a28d71f
             02004f 114d4d8ae1f800a427074f6dc55c2982 0f0801 f230d6876883e50d66e71fdb
             2e23feda01aef2f68a0acdafa844010c7313125585299a769d21b93b7fd41409172a2ff310ed8a9dc15e23c953edeed1
             4c2766e5d02bc6fc45efca781c581b6206bf5b67d5f988ee22779ec3bd1a8a47
整個檔案 SHA-256 = c935cf3d42a93c8baec2028d322acab2d8a50e078dd6aa51fb21d1a5f65cff09
```

（空白只是排版；檔頭是連續的位元組。）原型的 `test_spec_conformance_by_hand` 只用本節規格與標準原語把這個向量手動解開，
確認文件與程式一致。這是**自己產生**的回歸向量，不是第三方向量；第三方向量另測 RFC 7914（scrypt）與 RFC 5869（HKDF）。

---

## 6. 指令介面設計

### 6.1 指令

祕密（密語、金鑰）**不從命令列參數讀**（會出現在行程清單與歷史紀錄）：密語從終端機提示或 `--passphrase-file` 讀，金鑰從檔案讀。

| 指令 | 用途 | 例子 |
|---|---|---|
| `keygen` | 產生萬用鎖；私鑰以密語封存成私鑰檔，另輸出公鑰檔與指紋 | `mlock keygen --identity master.id --pub master.pub` |
| `session-keygen` | 產生一把 32 bytes 的本次金鑰檔 | `mlock session-keygen share.key` |
| `encrypt` | 建立檔案；**一定要**給萬用鎖公鑰 | `mlock encrypt report.pdf -o report.mlk --master master.pub --session share.key` |
| `decrypt` | 解密；先寫暫存檔，全部驗證通過才改名 | `mlock decrypt report.mlk -o report.pdf --session share.key` |
| `inspect` | 不需金鑰：版本、塊大小、槽清單、generation、fingerprint；`--verify-with` 時順便驗證檔頭 | `mlock inspect report.mlk --json` |
| `add-slot` | 用一把能開的鑰匙加槽 | `mlock add-slot report.mlk --with master.id --session new.key` |
| `remove-slot` | 移除槽（最後一個不能移；唯一萬用鎖槽要 `--allow-remove-master`） | `mlock remove-slot report.mlk --with master.id --slot 1` |
| `replace-slot` | 換槽（rewrap）：內容不動 | `mlock replace-slot report.mlk --with master.id --old-session share.key --session new.key` |
| `rekey` | 換 DEK、整份重新加密、重建所有槽 | `mlock rekey report.mlk --with master.id --master master.pub --session new.key` |
| `check-revoked` | 確認某把舊本次金鑰打不開這份檔案 | `mlock check-revoked report.mlk --old-session share.key` |

共通：寫入都先寫暫存檔再原子替換；`--in-place` 才覆蓋原檔，否則必須給 `-o`；`--json` 輸出機器可讀結果。

### 6.2 穩定的失敗代碼

結束碼＝10＋代碼數字（例如 `MLK-E05` → 15）；0＝成功、2＝參數用法錯誤。`--json` 時輸出 `{"code","name","hint"}`。
訊息裡**永遠不含**金鑰、密語或明文。

| 代碼 | 名稱 | 意思 | 補救建議 |
|---|---|---|---|
| MLK-E01 | NOT_MLOCK | 不是這個格式 | 確認選對檔案 |
| MLK-E02 | UNSUPPORTED_VERSION | 格式版本未知 | 用支援該版本的程式 |
| MLK-E03 | UNSUPPORTED_SUITE | 演算法組合未知／停用 | 不會自動退回（防降級） |
| MLK-E04 | MALFORMED_HEADER | 檔頭結構損毀或截斷 | 從備份或雲端版本紀錄取回 |
| MLK-E05 | NO_MATCHING_SLOT | 給的鑰匙打不開任何槽 | 鑰匙錯、已被換掉、或槽被改；改用萬用鎖 |
| MLK-E06 | HEADER_TAMPERED | 槽開了但檔頭驗證失敗 | 檔頭被改過；不要信任，從備份取回 |
| MLK-E07 | PAYLOAD_TAMPERED | 內容區塊驗證失敗 | 沒有輸出明文；從備份取回 |
| MLK-E08 | TRUNCATED | 在最後一塊之前就結束 | 重新下載完整檔案 |
| MLK-E09 | KDF_PARAMS_OUT_OF_RANGE | scrypt 參數太弱或太大 | 用萬用鎖開啟後重建該槽 |
| MLK-E10 | TOO_MANY_SLOTS | 超過 16 個槽 | 先移除不用的槽 |
| MLK-E11 | LAST_SLOT | 不能移除最後一個槽 | — |
| MLK-E12 | MASTER_SLOT_PROTECTED | 會移除唯一的萬用鎖槽 | 確定的話加 `--allow-remove-master` |
| MLK-E13 | NO_MASTER_SLOT | 新檔案沒有萬用鎖槽 | 加 `--master` |
| MLK-E14 | BAD_ARGUMENT | 參數不正確 | 看說明 |
| MLK-E15 | BAD_IDENTITY_FILE | 私鑰檔損毀或密語錯 | 改用另一份備份 |

注意：「鑰匙錯」與「槽被改」在密碼學上分不出來，所以都是 `MLK-E05`，訊息要兩種都提。

---

## 7. 金鑰輪替流程

### 7.1 情境 A：把檔案交給別人短期使用（最常見）

1. `session-keygen share.key` → `encrypt doc -o doc.mlk --master master.pub --session share.key`。
2. 把 `doc.mlk` 放雲端；`share.key` **走另一個管道**交給對方（不要跟檔案放在一起）。
3. 對方用完後：因為對方解開過，可能留著 DEK，所以做 **rekey**（不是只有換槽）：
   `rekey doc.mlk --with master.id --master master.pub [--session next.key]`。
4. 上傳新版，**刪除雲端上的舊版本與版本紀錄**；記下新的 `fingerprint` 與 `generation`。
5. 確認：`check-revoked doc.mlk --old-session share.key` 必須回報打不開（`MLK-E05`），`inspect` 的 `file_id` 必須變了。

### 7.2 情境 B：本次金鑰外洩，但確定還沒人用過

`replace-slot`（rewrap）即可，速度與檔案大小無關；同樣要刪除雲端舊版本。

### 7.3 情境 C：萬用鎖要換（定期或懷疑外洩）

1. `keygen` 產生新萬用鎖。
2. 對每個檔案：懷疑外洩 → `rekey`（新 DEK）；只是定期 → `replace-slot` 把舊萬用鎖槽換成新的。
3. 照 SOPS 的教訓：**先把舊鑰匙從槽裡拿掉，再換 DEK**；順序反了，中間被同步出去的版本仍可被舊鑰匙打開。
4. 舊萬用鎖私鑰在所有檔案都換完、確認新私鑰備份可用之後才銷毀；但任何仍存在的舊副本依然可以被舊萬用鎖打開。

### 7.4 「確認舊本次金鑰失效」做得到與做不到的

| 能確認 | 怎麼確認 |
|---|---|
| 新檔案用舊本次金鑰打不開 | `check-revoked`（用舊金鑰試開，預期 `MLK-E05`） |
| 槽清單已不含舊金鑰的槽 | 舊金鑰算出的 `key_id` 不在槽清單中 |
| 留著舊 DEK 的人開不了新檔 | rekey 後 `file_id` 改變（DEK 隨之換新） |
| 雲端目前那份是最新版 | `fingerprint`／`generation` 與自己紀錄的相同 |

| 做不到 | 原因 |
|---|---|
| 讓已複製走的舊檔案失效 | 舊檔案自帶舊槽，離線就能開（LUKS FAQ 6.7 同理） |
| 收回對方已看過或存下的明文 | 任何加密都做不到 |
| 確認雲端真的刪掉了舊版本 | 取決於雲端服務 |

---

## 8. 與 PGP（gpg）互通

| 選項 | 做法 | 優點 | 缺點 | 建議 |
|---|---|---|---|---|
| G1 gpg 槽（type `0x04`） | 加密時呼叫 `gpg --encrypt -r <萬用鎖 OpenPGP key>` 把 32 bytes DEK 加密，結果放進槽；開檔時呼叫 `gpg --decrypt` 取回 DEK | 萬用鎖可以放在 OpenPGP 智慧卡／USB 安全金鑰，私鑰**不能匯出**，中毒的電腦偷不走（只能趁插著時使用） | 依賴外部程式；OpenPGP 訊息內含收件人 key ID（可用 `--throw-keyids` 隱藏）；要處理 gpg 的錯誤碼 | 第二階段做（WP5） |
| G2 直接用 gpg 本身 | `gpg -e -r 萬用鎖 -r 對方 --symmetric`（或 age 的多收件人） | 不用寫程式、格式成熟 | gpg／age 沒有方便的換槽指令（推測）；age 不能混用密語與公鑰收件人（已查證） | 只是想要「萬用鎖能開」而不需要換槽、不需要整合進 Encrypter 時，最穩 |
| G3 外面再包一層 gpg | 整個 `.mlk` 再丟給 gpg | — | 又回到巢狀 | 不建議 |

DEK 不應該以明文形式交給 gpg 以外的地方；呼叫 gpg 時用管線（stdin/stdout）傳，不寫暫存檔。

---

## 9. 萬用鎖怎麼保管

目標：電腦中毒、硬碟壞掉、單一備份遺失時，萬用鎖都不會跟著沒了，也不會被偷。

| 建議 | 說明 |
|---|---|
| **公鑰型萬用鎖** | 日常電腦只放公鑰（加密用）；私鑰平常不在任何連網電腦上。這是「中毒不會一起沒了」最重要的一步。 |
| 私鑰離線產生 | 最好在離線或剛開機的乾淨環境 `keygen`，產生後只存密語封存的私鑰檔。 |
| 至少三份備份 | 兩支 USB 隨身碟（放不同地點）存**密語封存**的私鑰檔；一份紙本（私鑰的十六進位或 QR＋檢查碼）放保險箱。每年做一次「從備份取回」演練。 |
| 封存密語要強 | 6 個以上隨機字（diceware）；scrypt 參數用預設以上。 |
| 不要只靠「密語衍生的萬用鎖」 | 從密語直接算出萬用鎖很方便，但任何拿到一份檔案的人都能離線暴力猜它，而且一猜中就是全部檔案。若要用，必須是很長的隨機密語，且只當備援。 |
| 硬體金鑰（選配） | OpenPGP 智慧卡／USB 安全金鑰：私鑰不能匯出，搭配 §8 的 gpg 槽。仍需要備份方案（產生兩支或保留離線備份）。 |
| 門檻分持（選配） | 把萬用鎖私鑰分成 N 份、任 M 份可還原（Shamir）。只能用經過審查的實作，不要自己寫。 |
| 雲端不放私鑰 | 即使是封存過的私鑰檔也不建議放雲端：一旦封存密語弱，就是全部檔案的離線暴力目標。 |

關於「USB 在場證明」類工具（插著某支 USB 才允許操作）：這類工具通常做的是挑戰回應——電腦出一道新題目，
隨身碟上的金鑰簽名，並比對裝置序號。它擋得住「把金鑰檔隨手複製到別支隨身碟」、「重放舊的回應」，
拔掉後幾秒內權限失效；金鑰加密時，單獨被偷的隨身碟也沒用。但它**不保護金鑰本身**：電腦被控制時，
惡意程式可以讀走金鑰檔、在你插著時代簽任何題目，事後也不一定留下可發現的痕跡；能偽裝同一組序號的裝置也能通過。
（2026-11-13 修正：先前寫成「只證明那支隨身碟插著、可以被整支複製」，過於簡化。）
可以當作方便的操作閘門，但不能取代上面的離線備份與公鑰型萬用鎖。

---

## 10. 原型

位置：`tools/encrypter/prototype/master_lock/`（獨立目錄，不被 Encrypter 匯入、不進打包）。

| 檔案 | 內容 |
|---|---|
| `mlock.py` | 參考實作：`encrypt`、`decrypt`、`add_slot`、`remove_slot`、`replace_slot`、`rekey`、`find_slot`、`inspect`、`seal_identity`／`open_identity`、錯誤代碼表 |
| `test_mlock.py` | 44 個測試，全部離線，金鑰都在測試中產生 |

依賴：`cryptography` 50 以上（用到 `hazmat.primitives.hpke`）。Encrypter 的 requirements **沒有**它，
所以在 Encrypter 的 venv 裡跑 pytest 時，這個測試模組會自動略過，不影響既有測試。

執行：

```powershell
python -I -m unittest discover -s tools\encrypter\prototype\master_lock -t tools\encrypter\prototype\master_lock -v
```

測試涵蓋：

| 類別 | 內容 |
|---|---|
| 已知答案 | RFC 7914 scrypt 向量、RFC 5869 HKDF 向量、§5.7 格式向量、照規格手算解開向量 |
| 往返 | 三種槽各自能開；0、1、塊大小±1、多塊；預設 64 KiB 塊 |
| 錯金鑰 | 別的萬用鎖、別的本次金鑰、錯密語、沒給金鑰、拿公鑰當私鑰 |
| 竄改 | 檔頭**每一個位元組**翻轉都失敗；內容抽樣翻轉；區塊對調；整段檔頭移植；單一槽移植 |
| 截斷／附加 | 截在區塊邊界（`E08`）、截在塊中間（`E07`）、只剩檔頭、附加資料 |
| 降級 | 版本、suite、scrypt 參數（調低→`E09`；改成範圍內別的值→`E05`）、塊大小 |
| 換槽 | 換槽後舊本次金鑰打不開、新的與萬用鎖可以；內容位元組不變；generation＋1、fingerprint 改變 |
| 誠實的限制 | 舊副本用舊本次金鑰仍打得開；留下的 DEK 在換槽後仍能解內容、rekey 後不行；槽持有人也能改槽 |
| 保護 | 不能移除最後一個槽；唯一萬用鎖槽受保護；新檔案必須有萬用鎖；槽數上限 |
| 祕密不外洩 | 輸出不含 DEK、本次金鑰、密語、萬用鎖私鑰、明文；`repr`、錯誤訊息、`inspect` 都不含祕密 |

原型**沒有**做的：串流（整份在記憶體）、CLI、gpg 槽、簽章、補齊長度、檔名等中繼資料。

---

## 11. 建議的落地方式與工作包

前提：先等另一條線（Encrypter 的 CLI／介面改版）合併，再在 `dev/encrypter` 上做，避免衝突。

| 工作包 | 內容 | 驗收 |
|---|---|---|
| WP1 核心 | 把原型移成 `crypto_tool/core/mlock.py`，改為串流（暫存檔＋原子替換）；依 D3 決定用 PyCryptodome 或 `cryptography` | §5.7 向量逐位元組相同；原型的 44 個測試全部移植並通過；1 GB 檔案記憶體用量固定 |
| WP2 CLI | §6 的指令與結束碼，接到新的 CLI 架構 | 每個指令都有測試；錯誤輸出 JSON 正確 |
| WP3 GUI | 新分頁「萬用鎖」：建立／解密／分享（產生本次金鑰）／收回（rekey）／檢視 | 收回流程預設 rekey，並顯示「已複製走的舊檔無法收回」 |
| WP4 金鑰管理 | `keygen`、私鑰檔封存、紙本備份匯出（含檢查碼）、取回演練 | 從紙本還原後能開檔 |
| WP5 gpg 槽 | §8 G1 | 用測試用 gpg home（臨時目錄）跑往返 |
| WP6 舊檔轉換 | `.isd` → `.mlk`：用舊程式解開、用新格式加密 | 轉換後雜湊相同；舊檔不自動刪 |
| WP7 簽章（選配） | 擁有者用 Ed25519 簽檔頭＋內容雜湊，防槽持有人偽造 | 槽持有人改內容後簽章驗證失敗 |
| WP8 互通驗證 | 若 WP1 選 PyCryptodome：用 `cryptography` 寫的原型與 PyCryptodome 版互相解對方的檔案（含萬用鎖槽） | 雙向都能開 |

依賴注意：Encrypter 目前只用 PyCryptodome。它在 3.22 起有 HPKE（X25519、AES-256-GCM、`info`），也有 scrypt、HKDF、AES-GCM，
所以**可以不加新依賴**（`pycryptodome>=3.22,<4`）。若改用 `cryptography`，要照 repo 規則加主版本上限，
而 `cryptography` 主版本更新很快，上限得常常調。

---

## 12. 需要擁有者決定的事

每項都標出建議；沒有回覆時以建議為預設。

| # | 決定 | 選項 | 建議 |
|---|---|---|---|
| D1 | 萬用鎖用哪一種 | A. 公鑰型（X25519，私鑰離線）／B. 對稱金鑰檔（加密時也要用到它）／C. 由密語衍生 | **A**：日常加密不碰私鑰，中毒時偷不到 |
| D2 | 「收回分享」預設做什麼 | A. rekey（安全、整份重加密）／B. 只換槽（快，但擋不住留了 DEK 的人） | **A**；B 放在進階選項 |
| D3 | 落地用哪個函式庫 | A. PyCryptodome ≥3.22（不加新依賴）／B. 加入 `cryptography` | **A**，但要做 WP8 互通驗證 |
| D4 | 要不要自己做，還是直接用現成工具 | A. 做進 Encrypter（WP1～WP4）／B. 直接用 gpg 或 age 的多收件人，不寫程式 | 真正重要的資料先用 **B**；想整合進工具、需要便宜的換槽再做 **A** |
| D5 | 本次金鑰給對方的形式 | A. 32 bytes 隨機金鑰檔／B. 密語 | **A**；密語只在對方無法收檔案時用 |
| D6 | 是否做簽章（WP7） | A. 先不做／B. 一起做 | **A**，等 v1 穩定再說 |
| D7 | 萬用鎖備份方式 | A. 兩支 USB（密語封存）＋紙本／B. 再加硬體金鑰（gpg 槽）／C. 門檻分持 | **A**，之後視需要加 B |
| D8 | 原始檔名等中繼資料 | A. 不存（雲端只看到你取的檔名）／B. 加密後放在內容前段 | **A**；需要時再做 B |

---

## 13. 查證紀錄

已查證（本次讀過）：

- age 規格（file key、stanza、scrypt 不可混用與理由、檔頭 HMAC、STREAM 分塊與 nonce）：https://github.com/C2SP/C2SP/blob/main/age.md
- OpenPGP RFC 9580（PKESK／SKESK 多收件人、SEIPD v2 的 salt＋HKDF、分塊、最後驗證標籤）：https://www.rfc-editor.org/rfc/rfc9580.html
- GnuPG `--throw-keyids`：https://www.gnupg.org/documentation/manuals/gnupg/GPG-Esoteric-Options.html
- cryptsetup FAQ（8 個槽、換密語不換 master key、換 master key 要備份＋重新格式化、舊備份保有舊槽）：
  https://android.googlesource.com/platform/external/cryptsetup/+/refs/heads/main/FAQ （官方 wiki
  https://gitlab.com/cryptsetup/cryptsetup/-/wikis/FrequentlyAskedQuestions 本次無法讀取內文，改讀這份鏡像）
- SOPS 金鑰管理（`rotate`、`updatekeys`、移除外洩金鑰的順序）：https://getsops.io/docs/usage/key-management/
- Google Cloud KMS 信封加密與重新加密：https://docs.cloud.google.com/kms/docs/envelope-encryption 、
  https://docs.cloud.google.com/kms/docs/re-encrypt-data
- AWS KMS 信封加密與輪替：https://docs.aws.amazon.com/kms/latest/developerguide/kms-cryptography.html 、
  https://docs.aws.amazon.com/kms/latest/developerguide/rotate-keys.html
- HPKE RFC 9180：https://www.rfc-editor.org/rfc/rfc9180.html
- PyCryptodome HPKE API：https://www.pycryptodome.org/src/protocol/hpke
- `cryptography` 50.0.2 的 HPKE API：在本機直接檢查。

推測或未查證：

- age 沒有換槽指令、gpg 可用 `--override-session-key` 手動重包：依既有知識，本次未讀原文。
- PyCryptodome「3.22.0 加入 HPKE」：來自轉載版本紀錄的網站，未讀官方 changelog。
- PyCryptodome 與 `cryptography` 的 HPKE 互通：同為 RFC 9180，推測可互通，**未測**（WP8）。
- SOPS 的 MAC 細節（本次只讀到「MAC 以 data key 加密存放」的摘要，未讀原始碼）。
