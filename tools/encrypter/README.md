# Encrypter — CryptoTool Pro

把檔案或資料夾加密成**公開標準格式**的檔案。這個工具不見了，別的電腦用公開的工具一樣打得開。

| 模式 | 格式 | 副檔名 | 誰打得開 | 需要 |
|---|---|---|---|---|
| **簡單模式**（預設） | [age v1](https://c2sp.org/age) | `.age`（文字形式也是 `.age`） | 這個工具，或任何裝了 [age](https://age-encryption.org)／rage 的電腦 | 只要這個工具（`cryptography` 套件） |
| **PGP 模式** | OpenPGP（RFC 4880） | `.gpg`、文字形式 `.asc` | 這個工具，或 GnuPG、Gpg4win／Kleopatra 等任何 OpenPGP 程式 | **電腦上要有 `gpg`**（GnuPG 2.2 以上；Git for Windows、Gpg4win 都附） |

## 先講清楚（請先讀）

- **為什麼用公開格式**：自己排的格式沒有人審過，災難時還得靠這個工具才解得開。age 與 OpenPGP 都是公開規格、
  有好幾個獨立實作；加密檔可以交給任何人、任何電腦解，不必信任或保存這個程式。
- **age 的部分是自寫實作**：照公開規格、只用 `cryptography` 的標準原語（X25519、ChaCha20-Poly1305、HKDF、HMAC、scrypt）寫的，
  **通過官方 C2SP CCTV 測試向量（128 個）**，**但尚未經外部審閱；也還沒有用真的 age／rage 程式交叉測試**
  （這台開發電腦不執行網路上抓來的程式）。在交叉測試做完之前，重要資料請留著原檔。細節見 [docs/format-age.md](docs/format-age.md)。
- **PGP 模式需要系統有 `gpg`**：找不到時只有 PGP 模式不能用，簡單模式照常。每次操作用一個暫時的、專用的金鑰環資料夾，
  用完就刪，**不碰你自己的 gpg 金鑰環**。細節見 [docs/pgp-mode.md](docs/pgp-mode.md)。
- **這一版只加密、不簽章**：加密讓別人看不到內容；但不能證明「是誰做的」「有沒有被換掉一份同樣能解開的檔」。要簽章之後可以加（gpg 本身就能簽）。
- **鑰匙或密語不見，就永遠打不開**。沒有後門、沒有救援——除非當初也加了萬用鎖（見下面）。

## 萬用鎖：同一份檔案，別人用自己的鑰匙開，你用萬用鎖也能開

做法是兩種格式都內建的**多收件人**（信封加密）：內容只加密一次，只有一把很小的檔案金鑰被每把鎖各包一次。
**檔案不會變兩倍大**（下面有實測數字）。

**誰打得開？** 加密時列進去的**每一把鎖都能單獨打開整個檔案**：別人的鑰匙、你的每一把萬用鎖（PGP 模式還可以加一個密語）。
不需要湊齊好幾把，也不分主從；少了任何一把，其他把照樣能開。

**怎麼做（簡單模式）**

1. 產生萬用鎖：`keygen -o master.key --protect`（印出公鑰 `age1…`）。要幾把就跑幾次、每次換檔名
   （例如家裡電腦一把、筆電一把、離線備用一把）；每次都是全新的一把，**同名檔案已存在時不會覆蓋**。
2. 把萬用鎖的**公鑰**寫進專案的 `.env`，**好幾把用逗號分開**：`ENCRYPTER_MASTER_RECIPIENT=age1aaa…,age1bbb…`
   （或在視窗的「金鑰」分頁填，按「從身分檔讀…」會接在後面）。公鑰不是祕密；`.env` 裡只放公鑰與檔案路徑，**不要放私鑰本身**（程式讀到會拒絕）。
3. 加密時加 `--with-master`（設定裡的**每一把**都會加上；視窗裡有設定時預設就勾「也讓萬用鎖打得開」）。
   不想改設定時，也可以這次直接指定：`--master age1aaa… --master age1bbb…`（可以重複；也接受一行一把公鑰的清單檔）。
4. 要開的時候：`decrypt 檔.age -i master.key`（哪一把都可以）。

**自訂密碼的萬用鎖**

| 模式 | 能不能「別人的公鑰＋你自己訂的密碼」放在同一個檔案 | 怎麼做 |
|---|---|---|
| 簡單模式（age） | **不能直接放密語**：age 規格規定密語必須是檔案唯一的鎖（工具會拒絕並說明） | 用**密語保護的身分檔**當萬用鎖：`keygen -o master.key --protect`。萬用鎖本身是金鑰，但私鑰檔要先輸入你訂的密碼才能用——等於「拿著檔案＋知道密碼」才打得開。age 官方的 `age -d -i master.key` 也認得這種檔 |
| PGP 模式 | **可以**：同一個檔案同時有收件人公鑰與一個密語，任何一個都能開 | `encrypt 檔 --mode pgp --pgp-recipient 對方.public.asc --passphrase`（也可再加 `--with-master`）。解開：對方用自己的私鑰，你用 `decrypt 檔.gpg --passphrase` |

**大小實測**（1 MiB＝1,048,576 bytes 的隨機資料，2026-11-13）

| 模式 | 鎖 | 加密後 | 比原檔多 |
|---|---|---|---|
| 簡單模式 | 1 把收件人 | 1,049,016 | +440（標頭＋每 64 KiB 一個 16 bytes 驗證碼） |
| 簡單模式 | ＋1 把萬用鎖 | 1,049,114 | +538 |
| 簡單模式 | ＋2 把萬用鎖 | 1,049,212 | +636 |
| 簡單模式 | ＋3 把萬用鎖 | 1,049,310 | +734 |
| PGP 模式 | 1 把收件人 | 1,049,626 | +1,050 |
| PGP 模式 | ＋1 把萬用鎖 | 1,049,722 | +1,146 |
| PGP 模式 | ＋2 把萬用鎖 | 1,049,818 | +1,242 |
| PGP 模式 | ＋1 把萬用鎖＋你自訂的密語 | 1,049,770 | +1,194 |

每多一把鎖固定多約 **98 bytes**（age）／**96 bytes**（OpenPGP，ed25519／cv25519 金鑰；RSA 金鑰會多幾百 bytes），密語約 48 bytes；跟檔案大小無關。

**備份與保管**

- 萬用鎖的**私鑰檔**（`master.key`、PGP 的 `.secret.asc`）每一把都要在這台電腦以外留一份：隨身碟、另一台電腦、或印成紙本鎖起來。
  建議至少一把**離線**（平常不插著、不放在這台電腦上）。
- 私鑰檔一律 `--protect` 用密語保護，密語另外記（不要跟私鑰檔放在一起）。
- 公鑰（`age1…`、`.public.asc`）不是祕密，可以放 `.env`、可以給別人，用來「讓萬用鎖也打得開」。

**外洩的風險（請先想清楚）**

- 萬用鎖是「一把開全部」：任何一把萬用鎖的私鑰外洩（而且沒有密語保護，或密語也被猜到），**所有加了它的檔案**都會被打開。
  把數量控制在真的需要的幾把，用密語保護，離線保存。
- 懷疑某一把外洩：從設定拿掉那把公鑰（之後的新檔不再加它），重要的舊檔用 `rekey` 換成新的萬用鎖，並刪掉舊副本。
  已經被複製走的舊檔無法收回（見下面「誠實的限制」）。
- 萬用鎖不見（而且也沒有別的鑰匙）＝檔案永遠打不開；所以才建議主＋備兩把以上，分開存放。

**換人、換鎖：`rewrap` 與 `rekey` 的差別**

| | `rewrap`（換鎖） | `rekey`（換檔案金鑰） |
|---|---|---|
| 做什麼 | 用手上能開的鑰匙取出檔案金鑰，換一組收件人；**內容的位元組原封不動** | 解開後用**新的**檔案金鑰與新的收件人整份重新加密 |
| 速度 | 快（大檔也只重寫標頭，但預設會先把內容驗證一遍） | 跟重新加密一樣 |
| 舊鑰匙還能開新檔嗎 | 不能 | 不能 |
| 曾經解開過的人（記下了檔案金鑰） | **還能**解新檔 | 不能 |
| 支援 | 只有 age（gpg 沒有這個功能） | age、OpenPGP |

**誠實的限制（兩者都一樣）**：已經被複製走的**舊檔**不會失效——拿著舊副本的人用舊鑰匙照樣打得開，對方已經看過的內容也收不回來。
要讓舊鑰匙真的沒用：`rekey`，並刪掉所有舊副本。萬用鎖是「一把開全部」，它外洩就全部外洩，所以保管方式才是重點。

另外，**age 規格規定密語（scrypt）必須是唯一的鎖**：簡單模式不能「密語＋萬用鎖」。要這個組合請用 PGP 模式（OpenPGP 可以同一個檔同時有公鑰與密語），
或用上面「自訂密碼的萬用鎖」的做法（密語保護的身分檔）。工具遇到時會明確拒絕並這樣建議。

以上每一點都有測試：`tests/test_master_lock.py`（多把萬用鎖各自打得開、`--master` 重複、`keygen` 每次不同且不覆蓋、
密語保護的身分檔當萬用鎖、1 MiB 檔案每多一把只多固定大小、PGP「別人的公鑰＋自訂密語＋兩把萬用鎖」實際呼叫 gpg）。

## 多層（剝洋蔥）

每一層都是一個**完整、標準、自己說明自己**的加密檔；「夾帶旁邊的檔案」就是把上一層的加密檔和其他檔一起打包再加密：

```powershell
ct encrypt secret.txt -o secret.txt.age -r <丙的公鑰> --with-master
ct encrypt secret.txt.age side2.txt -o L2.tar.age -r <乙的公鑰> --with-master
ct encrypt L2.tar.age side1.txt -o L1.age -r <甲的公鑰> --with-master
```

- 擁有者：`ct decrypt L1.age -o 全部 -i master.key --all-layers` 一路解到底（每層都有萬用鎖）。
- 甲：`ct decrypt L1.age -o 甲看到的 -i 甲.key --all-layers` 解開第 1 層後停下，回報「**第 2 層需要別的鑰匙：L2.tar.age**（X25519 金鑰 2 把）」，
  那個檔原封不動留著，可以交給乙。
- `--all-layers` 的規則：解開後結果仍是加密檔，或資料夾**最上層**有加密檔，就用同一組鑰匙繼續解；最多 16 層、最多試 256 個內層檔。
  解不開的那層不算失敗（退出碼 0，`--json` 的 `complete` 是 `false`、`stopped` 列出第幾層、哪個檔、看得到的資訊）。

**為什麼不做「一路加密成一個檔、看不出有幾層」**：那是靠「別人不知道我怎麼包的」換安全，不符合密碼學的基本原則（安全只能來自鑰匙），
也不會更安全——AES／ChaCha20 加密一次就遠超過任何人能硬解的程度。每層各自標準，反而每一層都能用公開工具檢查、交給不同的人。

## 視窗

以下指令都在 PersonalToolZoo repo 根目錄執行。

```powershell
.\scripts\setup-venv.ps1 encrypter     # 建立環境（只要一次；之後 run.bat 會自動同步）
.\tools\encrypter\run.bat              # 開視窗（雙擊也可以）
```

四個分頁：**加密**（選東西 → 選模式 → 誰可以打開：密語、公鑰、萬用鎖 → 存哪裡）、**解密**（自動辨識格式、可勾「一路解到底」）、
**金鑰**（產生 age 身分檔與 PGP 金鑰對、設定萬用鎖、檢查鑰匙檔）、**關於**。檔案可以直接拖進去。
介面規格與驗收清單在 [docs/ui-spec.md](docs/ui-spec.md)。

## 命令列

**打包的 exe 沒有主控台，命令列一律從原始碼執行**（三種叫法，效果一樣）：

```powershell
# 1. 給別的程式呼叫：直接用工具環境裡的 python，後面接 crypto_tool 資料夾（從哪個目錄執行都可以）
.\tools\encrypter\.venv\Scripts\python.exe tools\encrypter\crypto_tool <指令> ...
# 2. 在 tools\encrypter 底下
.\.venv\Scripts\python.exe -m crypto_tool <指令> ...
# 3. 人自己用：會先幫你把環境準備好（失敗時 run.bat 會停下來等你按鍵，所以不適合給程式呼叫）
.\tools\encrypter\run.bat <指令> ...
```

### 用法速查（`ct` 代表上面第 1 種的前半段）

```powershell
ct keygen                                   # age 身分檔 → .decryption_code.env，印出公鑰 age1…（不印私鑰）
ct keygen -o D:\keys\me.key --protect       # 私鑰用密語保護（互動輸入兩次，或從標準輸入讀一行）
ct keygen --mode pgp -o D:\keys\me --name "我"   # me.public.asc＋me.secret.asc，印指紋

ct encrypt report.pdf -r age1…                        # → report.pdf.age
ct encrypt photos -r age1… --with-master              # 資料夾 → photos.tar.age
ct encrypt a.txt -r age1… --master age1<主> --master age1<備>   # 這次直接指定兩把萬用鎖
ct encrypt a.txt photos -o bundle.age -R people.txt   # 多個輸入一定要 -o；-R 是一行一把公鑰的清單
ct encrypt notes.txt --passphrase                     # 用密語（互動；被導向時從標準輸入讀）
ct encrypt notes.txt --mode pgp --pgp-recipient bob.public.asc --with-master --passphrase --armor

ct decrypt report.pdf.age -i me.key                   # → report.pdf（資料夾自動還原）
ct decrypt L1.age -o out -i master.key --all-layers   # 一路解到底
ct decrypt notes.txt.asc -i me.secret.asc --pgp-key-passphrase   # -i 也認得 OpenPGP 私鑰
ct inspect L1.age                                     # 不需要鑰匙：格式、幾把鎖、是不是文字形式
ct rewrap a.age -o b.age -i master.key -r age1<新的人> --with-master
ct rekey  a.age -o b.age -i master.key -r age1<新的人>
ct --check --json                                     # 離線自我檢查：cryptography、age 往返、gpg 版本、設定
```

### 參數

| 參數 | 用在 | 說明 |
|---|---|---|
| `-o`, `--output` | 全部 | 輸出位置。encrypt 只有一個輸入時可省略（名稱加 `.age`／`.gpg`／`.asc`，資料夾多 `.tar`）；decrypt 預設去掉副檔名（資料夾再去掉 `.tar`）；rewrap／rekey 必填 |
| `--mode age\|pgp` | encrypt、keygen | 預設 `age`。解密、inspect、rewrap、rekey 自動辨識 |
| `-r`, `--recipient age1…` | encrypt、rewrap、rekey | 收件人公鑰，可以給好幾個 |
| `-R`, `--recipients-file 檔` | 同上 | 一行一把 `age1…`（`#` 開頭是註解）；也接受自己的身分檔（用它的公鑰） |
| `--with-master` | 同上 | 加上 `.env` 設定的**全部**萬用鎖（`ENCRYPTER_MASTER_RECIPIENT`；PGP 模式用 `ENCRYPTER_MASTER_PGP_KEY`） |
| `--master 萬用鎖` | 同上 | 這次直接指定一把萬用鎖，可以重複：簡單模式是 `age1…` 或公鑰清單檔，PGP 模式是公鑰 `.asc` 檔。可以跟 `--with-master` 一起用，重複的只算一次 |
| `--pgp-recipient 公鑰.asc` | encrypt、rekey | PGP 模式的收件人公鑰檔，可以給好幾個 |
| `--passphrase`／`--passphrase-stdin` | encrypt、decrypt、rewrap、rekey | 用（舊的）檔案密語。兩個都是開關，**密語本身不能寫在參數裡** |
| `--new-passphrase` | rewrap、rekey | 新的鎖用密語 |
| `-i`, `--identity 檔` | decrypt、rewrap、rekey | age 身分檔（可為密語保護）或 OpenPGP 私鑰；可以給好幾個。沒給任何鑰匙時用 `.env` 的 `ENCRYPTER_IDENTITY_FILE`／`ENCRYPTER_PGP_SECRET_KEY` |
| `--pgp-secret 私鑰.asc`、`--pgp-key-passphrase` | decrypt、rewrap、rekey | OpenPGP 私鑰檔；私鑰有密語保護時加後者 |
| `--all-layers` | decrypt | 一路解到底（見「多層」） |
| `--keep-tar` | decrypt | 內容是資料夾時不解開，輸出 `.tar` |
| `--armor` | encrypt、rewrap、rekey | 文字形式（可貼在信件裡）；rewrap／rekey 預設沿用來源的形式 |
| `--protect`、`--name`、`--email`、`--key-type` | keygen | 密語保護；PGP 金鑰的名稱、信箱、種類（`ed25519` 預設、`rsa3072`、`rsa4096`） |
| `--force` | encrypt、decrypt、keygen、rewrap、rekey | 輸出檔已存在時覆蓋。已存在且非空的**資料夾**永遠不覆蓋 |
| `--key-file`、`--key-name`、`--key-env` | decrypt | **只為了解開 ISD2 預覽格式（已停用）的舊檔** |
| `--json` | 全部 | 標準輸出只印一行 JSON（見下） |

**需要好幾個密語時**（例如身分檔有密語保護、檔案也用密語），從標準輸入**一行一個、依這個順序**讀：
① 有密語保護的身分檔（依 `-i` 的順序，只有真的需要時）② OpenPGP 私鑰的密語（`--pgp-key-passphrase`）
③ 檔案密語（`--passphrase`）④ 新密語（`--new-passphrase`、`keygen --protect`）。在終端機互動時會逐一提示、隱藏輸入。

### 給程式看的輸出（`--json`）與退出碼

```json
{"ok": true, "data": {"action": "encrypt", "mode": "age", "format": "age", "inputs": ["..."], "output": "...", "payload": "file", "armored": false, "recipients": {"keys": 2, "passphrase": false, "master": true, "masters": 1}, "bytes_in": 1234, "bytes_out": 1452}}
{"ok": true, "data": {"action": "decrypt", "format": "age", "output": "...", "payload": "folder", "all_layers": true, "complete": false, "depth": 2, "layers": [...], "stopped": [{"depth": 2, "path": "L2.tar.age", "reason": "needs_other_key", "code": "wrong_key", "lock": {"format": "age", "recipient_types": {"X25519": 2}}}]}}
{"ok": false, "error": {"code": "wrong_key", "reason": "提供的私鑰都不是這個檔案的收件人。", "retryable": false, "remedy": {"kind": "needs_config", "action": "..."}, "detail": "no-match"}}
```

判斷請看 `ok`、`error.code` 與退出碼，不要比對文字。

| 退出碼 | 意思 | `error.code` |
|---|---|---|
| 0 | 成功（`--all-layers` 停在某層也是 0，看 `complete`） | — |
| 2 | 這次的輸入有問題 | `bad_input`、`input_missing`、`output_exists`、`key_missing`、`bad_key_format`、`unsupported_format`、`legacy_format`、`unsafe_archive` |
| 3 | 環境沒裝好（缺 `cryptography`；PGP 模式找不到 gpg） | `dependency_missing` |
| 5 | 鑰匙或密語不對 | `wrong_key` |
| 6 | 加密檔被改過、截斷或損壞 | `corrupt` |
| 1 | 其他（讀寫失敗、程式錯誤） | `io_error`、`internal_bug` |

不加 `--json` 時，成功訊息印到標準輸出，失敗的原因與「怎麼辦」印到標準錯誤。

### 行為上要知道的

- 輸出先寫到目標旁邊的暫存檔（`.名稱.partial-xxxx`），全部驗證通過才改名；失敗會把暫存檔刪掉。
- 資料夾或多個輸入先打包成標準 tar：簡單模式邊打包邊加密，明文 tar 不落地；PGP 模式要先寫一個暫存 tar（gpg 只吃檔案），
  完成或失敗都會刪掉。解密時解出的 tar 也會先暫存在輸出位置旁邊，解開後刪掉。程式被強制結束時這些暫存檔可能留下，名稱都是 `.…partial-…`。
- 打包時不跟著連結走：捷徑、符號連結會被略過並回報（`skipped_links`）；tar 裡不放帳號名稱。
  用 age 官方工具解開資料夾時：`age -d -i me.key photos.tar.age | tar x`（內容在 tar 的最上層，不會多一層資料夾）。
- 解開資料夾時只接受一般的檔案與資料夾，路徑必須在輸出資料夾底下，Windows 保留名稱（CON、NUL…）拒絕；其他情況整個拒絕（`unsafe_archive`）。
  **內容是不是 tar 是看內容判斷的**：自己加密一個 `.tar` 檔，解開時也會被還原成資料夾，要原樣拿回請加 `--keep-tar`。
- `rewrap` 預設先把整份內容驗證一遍才換鎖，損壞的檔案不會被換鎖。
- 舊的 `.isd`：`inspect` 認得，`decrypt` 回 `legacy_format`，要用視窗的舊版工具。
- **ISD2 預覽格式（已停用）**：0.4.0 之前在開發線上做過、從沒發版的自有格式（64 bytes 檔頭）。**只能解密，不能再產生**：
  `decrypt` 自動辨識，用 `--key-file`／`--key-env`（舊的金鑰檔）或 `--passphrase`。設計稿裡另一個同名的「金鑰槽版 ISD2」從來沒有實作，**未採用**。
  見 [docs/legacy-modes.md](docs/legacy-modes.md)。

## 設定（`.env`）

跟 repo 其他工具一樣放專案的 `.env`（從原始碼執行是 repo 根目錄的 `.env`；打包的 exe 是 exe 旁邊的 `.env`）。範本在 repo 根目錄的 `.env.example`。

| 鍵 | 內容 |
|---|---|
| `ENCRYPTER_MASTER_RECIPIENT` | 萬用鎖的公鑰 `age1…`（公鑰不是祕密）；**好幾把用逗號分開**（設成環境變數時也可以一行一把） |
| `ENCRYPTER_MASTER_PGP_KEY` | PGP 模式的萬用鎖：OpenPGP **公鑰檔**的路徑；好幾個用分號 `;` 分開 |
| `ENCRYPTER_IDENTITY_FILE` | 解密時沒給鑰匙就用這個 age 身分檔（**只放路徑**） |
| `ENCRYPTER_PGP_SECRET_KEY` | 同上，OpenPGP 私鑰檔的路徑 |
| `ENCRYPTER_GPG`、`ENCRYPTER_GPG_TMPDIR` | 指定 gpg 執行檔、暫時金鑰環資料夾的上層（平常不用設） |

相對路徑以那個 `.env` 所在的資料夾為準；環境變數優先於 `.env`。

## 金鑰要怎麼放

- **私鑰（身分檔）一定要在這台電腦以外的地方另外留一份**：隨身碟、另一台電腦，或印成紙本鎖起來。
  只放在這台電腦，硬碟壞掉或重灌就全沒了。建議至少一把**離線**的萬用鎖，平常不插著、不放在這台電腦上。
- 身分檔不要跟加密檔放在同一個資料夾、同一個隨身碟或同一個雲端——放在一起就等於沒鎖。
- 身分檔建議用密語保護（`keygen --protect`）；這是 age 的標準做法，`age -d -i` 也認得。
- 身分檔不要進版控。這個 repo 的 `.gitignore` 擋了 `*.env`；身分檔用別的副檔名（`.key`）時要自己確認。
- 用密語的話，選一句長的（至少 12 個字，越長越好）；工具不會幫你記，也查不回來。

### 已知的限制

- 加密檔的大小大致等於原本的大小，看得出資料量；用的是密語還是金鑰、有幾把鎖，不需要鑰匙也看得到（OpenPGP 還看得到收件人的 key ID）。
- 不能證明「是誰加密的」（這一版不簽章）。拿得到公鑰的人都能做出一個解得開的檔。
- 密語太好猜的話，拿到加密檔的人可以離線一直猜；scrypt 只能拖慢，不能阻止。
- 這台電腦如果已經被入侵，任何加密工具都保護不了正在使用中的明文與金鑰。
- age：不支援外掛、SSH 金鑰、後量子收件人（遇到時明確說不支援）。PGP：只在 Git for Windows 附的 GnuPG 2.4.9 實測過。

## 版本紀錄

這個 repo 沒有工具層的 CHANGELOG，版本紀錄寫在這裡（tag 由 `release.ps1` 打）。

### 0.4.0（還沒發版：在 `dev/encrypter`，待合併、打包、驗收）

- **只產生兩種公開標準格式**：簡單模式＝age v1（預設，自寫實作，通過 C2SP CCTV 官方測試向量 128 個）、PGP 模式＝OpenPGP（呼叫系統 gpg）。
- 萬用鎖（多收件人；可以同時綁好幾把：設定用逗號分開、命令列可重複 `--master`）、`rewrap`（換鎖不重新加密）、`rekey`（換檔案金鑰整份重新加密）、`decrypt --all-layers`（剝洋蔥一路解到底）。
- 命令列：`encrypt`（多個輸入、資料夾）、`decrypt`（自動辨識格式）、`inspect`（舊名 `info`）、`keygen`（age 身分檔／PGP 金鑰對）、
  `rewrap`、`rekey`、`--check`、`--version`；`--json` 合約與退出碼沿用。
- 新視窗：兩種模式、誰可以打開（密語／公鑰／萬用鎖）、一路解到底、金鑰分頁（產生金鑰、設定萬用鎖）。
- 設定放專案 `.env`（萬用鎖公鑰、預設身分檔路徑）。
- 開發線上的自有格式改稱「ISD2 預覽格式（已停用）」，只能解密。舊 `.isd` 照舊在舊版工具。
- PGP 模式：gpg 的暫時金鑰環資料夾路徑固定補成 64 個字元（Git for Windows 的 GnuPG 2.4.9 在某些路徑長度下，
  沒有密語保護的 Curve25519 私鑰會解不開；細節見 [docs/pgp-mode.md](docs/pgp-mode.md)）。

### 0.3.0（tag `Encrypter_v0.3.0`）

- 第一個正式版，內容是開發期的迭代 1.4（`.isd` 格式、十一種演算法、Mixture、PGP 實驗、大檔分段），現在收在「關於 → 開啟舊版工具」。

---

## 交接

| 項目 | 內容 |
|---|---|
| 入口 | `crypto_tool/GUI__Encrypter.py`：沒有參數 → 開視窗；有參數 → 命令列（`sealed/cli.py`）。它把 `crypto_tool/` 加進 `sys.path`，所以視窗與命令列是以頂層的 `gui`、`sealed`、`agefmt`、`pgpmode` 載入；測試則是 `crypto_tool.…`。新模組的 `..` 相對匯入都有 `except ImportError` 退回頂層名稱，兩種方式下 `SealError` 各只有一個類別。命令列另有 `crypto_tool/__main__.py`（`python -m crypto_tool`） |
| 程式分區 | `crypto_tool/agefmt/`：age v1 格式（自寫，見 `docs/format-age.md`）。`crypto_tool/pgpmode/`：OpenPGP（呼叫 gpg，見 `docs/pgp-mode.md`）。`crypto_tool/sealed/`：`workflow.py` 整合層（命令列與視窗共用）、`cli.py` 命令列、`packing.py` 打包／解包、`settings.py` .env 設定、`errors.py` 錯誤代碼；`container.py`／`ops.py`／`keys.py` 是 ISD2 預覽格式（已停用，只能解密）。`crypto_tool/gui/app.py`（視圖）、`logic.py`（邏輯，不碰 tkinter）、`texts.py`（文案）、`theme.py`。`crypto_tool/core/`、`gui/tab_*.py`、`gui/widgets.py`、`gui/legacy_app.py`：舊版，**不要改**。`prototype/master_lock/`：萬用鎖研究原型，不打包、不被匯入 |
| 版本號 | `crypto_tool/_version.py` 的 `__version__`（0.4.0，用 `scripts/bump-version.ps1` 改的）→ exe 檔名 `GUI__Encrypter(vX.Y.Z).exe`、視窗標題 `CryptoTool Pro vX.Y.Z` |
| 環境 | 專屬 `tools\encrypter\.venv`（build／run 時自動建立與同步） |
| 依賴 | `cryptography>=42,<51`（age 與 ISD2 預覽格式）、`pycryptodome`（只剩舊版在用）、`ttkbootstrap>=1.10.1,<2`、`tkinterdnd2`；PGP 模式另外需要系統上的 `gpg`（不是 Python 套件）。ttkbootstrap **不能升 2.x**：2.x 打包後缺 `assets\icons\bootstrap.ttf`，exe 一開就崩潰 |
| 打包額外內容 | 無（`tool.json` 沒有 include）。`tests/`、`prototype/`、`docs/` 不打包 |
| 測試 | `.\tools\encrypter\.venv\Scripts\python.exe -m unittest discover -s tools\encrypter\tests -v`（只用標準庫 unittest；不開視窗、不連網、不開網路埠；PGP 的測試實際呼叫 gpg、約 2 分鐘，找不到 gpg 就略過）。另見下面「現況」的數字 |
| Release tag | `Encrypter_vX.Y.Z` |
| 文件 | [docs/format-age.md](docs/format-age.md)、[docs/pgp-mode.md](docs/pgp-mode.md)、[docs/ui-spec.md](docs/ui-spec.md)、[docs/legacy-modes.md](docs/legacy-modes.md)、[docs/master-lock-research.md](docs/master-lock-research.md)（研究，已落地）、[docs/handoffs/](docs/handoffs/) 交接單（格式決定見 `20261113-013906-format-decision-age-openpgp.md`） |

常用指令（repo 根目錄）：

```powershell
.\scripts\build.ps1 enc                 # build + 冒煙測試（會在桌面跳出視窗 10 秒）
.\scripts\release.ps1 enc keep -Yes     # 版本已經是 0.4.0：只 build＋打 tag，不再改版號
```

### 現況（2026-11-13，`dev/encrypter`，還沒合併回 master、還沒打包、還沒發版）

- 整合完成：合併了 `dev/encrypter-age`（age 核心）、`dev/encrypter-pgp`（PGP 模式）、`research/master-lock`（研究與原型）；
  命令列、視窗、設定、ISD2 預覽格式改成唯讀都做完，版本 0.4.0。
- 測試（2026-11-13，Python 3.11.9＋cryptography 50.0.2＋GnuPG 2.4.9，這台電腦沒有 pycryptodome 與 ttkbootstrap）：**225 個，221 過**、2 個錯誤、2 個略過（細節見交接單 `20261113-013906-…` 的「驗證」）。
  `test_mixture_modes`、`test_xorfold` 兩個舊測試因為缺 pycryptodome 匯入失敗（一直如此，不是這次造成的）。
- **還沒做的驗證**：① 畫面沒有人實際看過（`docs/ui-spec.md` 最後的清單）；② 這個工具自己的 `.venv` 還沒建、`build.ps1 enc` 還沒跑
  （這台電腦不能從網路安裝套件）；③ **沒有用真的 age／rage 交叉測試**（這台不執行網路上抓來的程式）；④ Gpg4win（原生版 gpg）沒有實測。
  擁有者在有網路的電腦上要跑的確切指令在交接單 `20261113-013906-…` 的「擁有者的步驟」。
- 合併分支裡有幾個 `test(encrypter): …` 標題的 commit，AGENTS.md 的 commit 類型沒有 `test`；沒有改寫歷史，記在這裡。

### 注意事項

- **不要自己發明格式或密碼學步驟**。要新功能（簽章、更多收件人種類）就用 age／OpenPGP 規格裡現成的東西。
- age 實作**不要改出規格之外的行為**；改了 `agefmt/` 一定要跑 `test_age_vectors.py`（官方向量，比對 SHA256SUMS）。
- **不要讓密語能從命令列引數傳入**，不要在任何輸出或錯誤訊息裡放金鑰、密語、明文；argparse 的錯誤訊息會把使用者打的引數帶出來，所以命令列故意不轉述它。
- `.env` 的設定只放公鑰與路徑；`settings.py` 讀到私鑰會拒絕。
- 主視窗不放 Mixture、迭代次數、XOR、Base64 這些舊選項（測試會擋）。PGP 模式是新的 OpenPGP，跟舊版的 PGP 實驗（`core/pgp.py`，不是 OpenPGP）無關。
- **版本號以 `_version.py` 為準**：`crypto_tool/README.md` 和 `crypto_tool/dev_plan.md` 裡的 1.0～1.4 是開發期間（2026-04-20～23）的內部迭代編號，不要用 1.x。
- `crypto_tool/gui/pgp_demo.py` 是開發用的舊 PGP 示範視窗，不在視窗程式裡。
- `del_dev_plan.md`、`crypto_tool/dev_plan.md`、`crypto_tool/README.md`、`docs/experiment.md` 是舊版的開發計畫／實驗紀錄，保留原樣。
