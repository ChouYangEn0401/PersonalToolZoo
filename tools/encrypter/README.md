# Encrypter — CryptoTool Pro

> **尚未經過外部審閱（2026-11-12）。** 新格式用的加密元件都是標準、經過公開審查的，但「怎麼把它們組成一個檔案格式」是這個工具自己排的，
> 還沒有給有密碼學經驗的人看過，也還沒有發版。**在那之前，不要把它當成唯一一份重要資料的保護手段**（原檔要留著）。
> 同一天另有一批設計文件建議改用公開的 age 格式，這件事還沒決定，見 [docs/handoffs/](docs/handoffs/) 的
> `…-encrypter-intent-and-redesign.md`「兩批文件不一致的地方」與 `…-workpackages-and-decisions.md` 的 Q1。

把檔案或資料夾加密成一個 `.isd2` 檔，只有你的密語或金鑰檔打得開。有視窗，也有命令列（給別的程式呼叫）。

- **加密方式**：標準的認證加密（AES-256-GCM，或 ChaCha20-Poly1305）；密語用 scrypt 轉成金鑰。沒有自己發明的演算法，也沒有多層疊加。
- **會明確失敗**：金鑰不對、檔案被改過、被截斷，解密都會失敗並說出原因，不會吐出錯的內容，也不會留下半個輸出檔。
- **不會幫你做危險的事**：輸出位置已經有東西就拒絕（要明確說覆蓋）；原檔不會被刪；金鑰、密語、明文不會出現在任何輸出裡。
- **舊版功能還在**：以前的 `.isd` 格式、Mixture、PGP、大檔分段收在視窗的「關於 → 開啟舊版工具」，只建議用來解開舊檔。
  原因與救回方法見 [docs/legacy-modes.md](docs/legacy-modes.md)。

## 視窗

以下指令都在 PersonalToolZoo repo 根目錄執行。

```powershell
.\scripts\setup-venv.ps1 encrypter     # 建立環境（只要一次；之後 run.bat 會自動同步）
.\tools\encrypter\run.bat              # 開視窗（雙擊也可以）
```

四個分頁：**加密**（選東西 → 選密語或金鑰檔 → 存哪裡 → 加密）、**解密**、**金鑰**（產生與檢查金鑰檔）、**關於**。
檔案與資料夾可以直接拖進去。介面規格與驗收清單在 [docs/ui-spec.md](docs/ui-spec.md)。

## 命令列

四個子指令：`encrypt`、`decrypt`、`info`、`keygen`。三種叫法，效果一樣：

```powershell
# 1. 給別的程式呼叫：直接用工具環境裡的 python，後面接 crypto_tool 資料夾（從哪個目錄執行都可以）
.\tools\encrypter\.venv\Scripts\python.exe tools\encrypter\crypto_tool <子指令> ...

# 2. 在 tools\encrypter 底下
.\.venv\Scripts\python.exe -m crypto_tool <子指令> ...

# 3. 人自己用：會先幫你把環境準備好（失敗時 run.bat 會停下來等你按鍵，所以不適合給程式呼叫）
.\tools\encrypter\run.bat <子指令> ...
```

下面的例子用 `ct` 代表上面第 1 種的前半段。

```powershell
# 產生一把金鑰（只印路徑與指紋，不印金鑰）
ct keygen -o D:\keys\.decryption_code.env

# 加密一個檔案 → report.pdf.isd2（放在原檔旁邊）；加密一個資料夾 → photos.isd2
ct encrypt report.pdf --key-file D:\keys\.decryption_code.env
ct encrypt photos      --key-file D:\keys\.decryption_code.env -o E:\backup\photos.isd2

# 解密（資料夾會還原成資料夾）
ct decrypt report.pdf.isd2 --key-file D:\keys\.decryption_code.env -o restored.pdf

# 用密語：從標準輸入讀一行。互動時會隱藏輸入並要求輸入兩次
ct encrypt notes.txt --passphrase-stdin

# 金鑰放在環境變數（由呼叫的程式設定），給的是變數的「名稱」
ct decrypt notes.txt.isd2 --key-env MY_TOOL_KEY -o notes.txt

# 看一個加密檔的資訊（不需要金鑰）
ct info report.pdf.isd2
```

### 參數

| 參數 | 用在 | 說明 |
|---|---|---|
| `-o`, `--output` | encrypt／decrypt／keygen | 輸出位置。encrypt 預設是「輸入名稱 + `.isd2`」；decrypt 預設是去掉 `.isd2` |
| `--key-file <路徑>` | encrypt／decrypt | 金鑰檔（格式見下） |
| `--key-name <名稱>` | 搭配 `--key-file` | 金鑰檔裡有好幾行時，指定要用哪一個名稱 |
| `--key-env <名稱>` | encrypt／decrypt | 從這個名稱的環境變數讀金鑰 |
| `--passphrase-stdin` | encrypt／decrypt | 從標準輸入讀一行密語（UTF-8） |
| `--cipher` | encrypt | `aes-256-gcm`（預設）或 `chacha20-poly1305` |
| `--force` | encrypt／decrypt／keygen | 輸出檔已存在時覆蓋。已存在且非空的**資料夾**永遠不覆蓋 |
| `--keep-tar` | decrypt | 內容是資料夾時不解開，輸出 `.tar` 檔 |
| `--format env\|raw`、`--name` | keygen | 金鑰檔的格式（預設 `env`）與名稱（預設 `CRYPTO_TOOL_KEY`） |
| `--json` | 全部 | 標準輸出只印一行 JSON（見下） |

三種金鑰來源必須選一種，而且只能選一種。**密語沒有辦法放在命令列引數**（會留在指令歷史裡）；沒有 `--passphrase <密語>` 這種寫法。

### 金鑰檔的格式

- **`.env` 風格**（`keygen` 預設產生這種，例如 `.decryption_code.env`）：

  ```
  # 註解
  CRYPTO_TOOL_KEY=b64:<32 bytes 的 base64>
  ```

  有好幾行時用名稱是 `CRYPTO_TOOL_KEY` 的那一行，或用 `--key-name` 指定；只有一行時直接用那一行。
  值可以是 `b64:`／`hex:` 開頭的 32 bytes 金鑰，或沒有前綴的 64 個十六進位字元／32 bytes 的 base64；
  **其他內容一律當成密語**（會經過 scrypt）。
- **剛好 32 bytes 的二進位檔**（`keygen --format raw`）。
- **只有一行文字的檔案**：規則同上面的「值」。

### 給程式看的輸出（`--json`）與退出碼

```json
{"ok": true, "data": {"action": "encrypt", "input": "...", "output": "...", "payload": "file", "cipher": "aes-256-gcm", "kdf": "raw-key", "bytes_in": 1234, "bytes_out": 1314}}
{"ok": false, "error": {"code": "wrong_key", "reason": "金鑰或密語不對（或檔頭被改過），無法解密。", "retryable": false, "remedy": {"kind": "needs_config", "action": "確認用的是當初加密這個檔案的那一把金鑰或密語。"}, "detail": ""}}
```

判斷請看 `ok`、`error.code` 與退出碼，不要比對文字。

| 退出碼 | 意思 | `error.code` |
|---|---|---|
| 0 | 成功 | — |
| 2 | 這次的輸入有問題 | `bad_input`、`input_missing`、`output_exists`、`key_missing`、`bad_key_format`、`unsupported_format`、`legacy_format`、`unsafe_archive` |
| 3 | 環境沒裝好 | `dependency_missing` |
| 5 | 金鑰或密語不對 | `wrong_key` |
| 6 | 加密檔被改過、截斷或損壞 | `corrupt` |
| 1 | 其他（讀寫失敗、程式錯誤） | `io_error`、`internal_bug` |

不加 `--json` 時，成功訊息印到標準輸出，失敗的原因與「怎麼辦」印到標準錯誤。

### 行為上要知道的

- 輸出先寫到目標旁邊的暫存檔（`.名稱.partial-xxxx`），全部成功才改名；失敗會把暫存檔刪掉。
- 加密資料夾時不跟著連結走：捷徑、符號連結會被略過，並在結果裡回報略過了幾個（`skipped_links`）。
- 解開資料夾時只接受一般的檔案與資料夾、而且路徑必須在輸出資料夾底下；其他情況整個拒絕（`unsafe_archive`）。
- 命令列不處理舊的 `.isd`（`info` 認得出來，`decrypt` 會回 `legacy_format`），要用視窗的舊版工具。
- 打包的 exe 是視窗程式、沒有主控台，命令列請從原始碼執行（上面三種叫法）。

## 金鑰要怎麼放

**金鑰或密語不見，加密的東西就永遠打不開；沒有後門，也沒有救援方法。**

- **一定要在這台電腦以外的地方另外留一份**：隨身碟、另一台電腦，或印成紙本鎖起來。
  只放在這台電腦，硬碟壞掉或重灌就全沒了。`keygen` 會印一個「金鑰指紋」，用來核對備份的是不是同一把。
- 金鑰檔不要跟加密檔放在同一個資料夾、同一個隨身碟或同一個雲端——放在一起就等於沒鎖。
- 金鑰檔不要進版控。這個 repo 的 `.gitignore` 擋了 `*.env`；在別的專案裡使用時，要自己確認那邊也有擋。
- 用密語的話，選一句長的（至少 12 個字，越長越好）；工具不會幫你記，也查不回來。
- 換金鑰＝舊金鑰加密的檔案要先解開、再用新金鑰重新加密。`keygen` 預設不會覆蓋既有的金鑰檔。

### 已知的限制

- 加密檔的大小大致等於原本的大小，看得出資料量；用的是密語還是金鑰檔、內容是檔案還是資料夾，不需要金鑰也看得到。
- 不能證明「是誰加密的」（這不是簽章）。拿得到金鑰的人都能做出一個解得開的檔。
- 密語太好猜的話，拿到加密檔的人可以離線一直猜；scrypt 只能拖慢，不能阻止。
- 一個檔只有一把鑰匙：不能讓好幾個人各用自己的鑰匙解，換鑰匙要重新加密。
- `--key-env` 會讓金鑰出現在環境變數裡，同一個行程啟動的子行程都看得到；能用金鑰檔就用金鑰檔。
- 這台電腦如果已經被入侵，任何加密工具都保護不了正在使用中的明文與金鑰。

## 檔案格式（ISD2）

64 bytes 的檔頭（格式版本、加密法、金鑰來源、內容種類、分塊大小、scrypt 參數、隨機 salt、nonce 前綴、金鑰檢查碼）
後面接一塊一塊的密文（預設每塊 1 MiB，各帶 16 bytes 驗證碼）。整個檔頭參與每一塊的驗證；
nonce 裡有塊的序號與「是不是最後一塊」，所以改動、對調、截斷、在結尾加東西都會被發現。
密語經 scrypt（N=2^17、r=8、p=1）變成主金鑰，再用 HKDF-SHA256 加上每個檔案隨機的 salt 導出這個檔案的金鑰。
逐欄位的說明在 `crypto_tool/sealed/container.py` 開頭。

---

## 交接

| 項目 | 內容 |
|---|---|
| 入口 | `crypto_tool/GUI__Encrypter.py`：沒有參數 → 開視窗；有參數 → 命令列（`sealed/cli.py`）。它會把 `crypto_tool/` 加進 `sys.path`，所以視窗相關的程式用 `from gui...`、`from core...`、`from sealed...`、`from _version...`。命令列另有 `crypto_tool/__main__.py`（`python -m crypto_tool`） |
| 程式分區 | `crypto_tool/sealed/`：現行格式（`container.py` 格式、`keys.py` 金鑰來源、`ops.py` 檔案與資料夾、`cli.py` 命令列、`errors.py` 錯誤代碼）；只依賴 `cryptography`，不 import `core`。<br>`crypto_tool/gui/app.py`（視圖）、`logic.py`（邏輯，不碰 tkinter）、`texts.py`（文案）、`theme.py`。<br>`crypto_tool/core/`、`gui/tab_*.py`、`gui/widgets.py`、`gui/legacy_app.py`：舊版，**不要改** |
| 版本號 | `crypto_tool/_version.py` 的 `__version__` → exe 檔名 `GUI__Encrypter(vX.Y.Z).exe`、視窗標題 `CryptoTool Pro vX.Y.Z` |
| 環境 | 專屬 `tools\encrypter\.venv`（build／run 時自動建立與同步） |
| 依賴 | `cryptography>=42,<51`（現行格式）、`pycryptodome`（只剩舊版在用）、`ttkbootstrap>=1.10.1,<2`、`tkinterdnd2`。ttkbootstrap **不能升 2.x**：2.x 打包後缺 `assets\icons\bootstrap.ttf`，exe 一開就崩潰 |
| 打包額外內容 | 無（`tool.json` 沒有 include） |
| 測試 | `.\tools\encrypter\.venv\Scripts\python.exe -m unittest discover -s tools\encrypter\tests -v`（83 個：新格式與命令列 57、新介面 19、舊版 7；只用標準庫，不需要另外裝 pytest；不開視窗、不連網） |
| Release tag | `Encrypter_vX.Y.Z` |
| 文件 | [docs/ui-spec.md](docs/ui-spec.md) 介面規格；[docs/legacy-modes.md](docs/legacy-modes.md) 舊功能；[docs/handoffs/](docs/handoffs/) 交接單 |

常用指令（repo 根目錄）：

```powershell
.\scripts\build.ps1 enc                 # build + 冒煙測試
.\scripts\release.ps1 enc minor         # 發新版
```

### 現況（2026-11-12，`dev/encrypter`，還沒合併、還沒發版）

- 命令列、新格式、新介面都寫好了，新測試 76 個全過（在另一個有 `cryptography` 的 Python 3.11 上跑的）。
- **還沒做的驗證**：① 畫面沒有人實際看過——要在真的電腦上跑 `run.bat`，照 `docs/ui-spec.md` 最後的清單看一遍；
  ② 這個工具自己的 `.venv` 還沒裝過 `cryptography`，舊的 7 個測試這一輪沒跑；③ `build.ps1 enc` 還沒跑
  （新增了 `cryptography`，要確認打包後開得起來）。
- **還沒決定的事**：加密檔的格式要維持現在這版、還是換成公開的 age 格式（同一天另一批設計文件的建議）。
  決定前不要用它加密要長期保存的真資料。差異與選項在 `docs/handoffs/20261112-223325-encrypter-intent-and-redesign.md`。
- 版本號還是 0.3.0。合併回 master 後建議用 `release.ps1 enc minor` 發 0.4.0。

### 注意事項

- **格式還沒定案**（見最上面的標示與交接單的選項表第一題）。定案並發版**之後**就不要再改檔頭排法：要改就升格式版本，
  舊版本照樣要解得開；`tests/test_sealed_container.py` 有一個釘住位元組的已知答案測試會擋。
  定案之前還沒有真實檔案用它，容器（`sealed/container.py`）可以整個換掉。
- **不要讓密語能從命令列引數傳入**，不要在任何輸出或錯誤訊息裡放金鑰、密語、明文；
  argparse 的錯誤訊息會把使用者打的引數帶出來，所以命令列故意不轉述它。
- 主視窗不放 Mixture、迭代次數、XOR、Base64、PGP 這些選項（測試會擋）。
- **版本號以 `_version.py` 為準**：`crypto_tool/README.md` 和 `crypto_tool/dev_plan.md` 裡的 1.0～1.4
  是開發期間（2026-04-20～23）的內部迭代編號；第一個正式版是 v0.3.0（tag `Encrypter_v0.3.0`，已推上 GitHub），
  內容就是迭代 1.4。下一版從 0.3.x／0.4.0 接著發，不要用 1.x。
- `crypto_tool/gui/pgp_demo.py` 是開發用的 PGP 示範視窗，不在視窗程式裡，
  要在 `tools\encrypter` 底下用 `python -m crypto_tool.gui.pgp_demo` 跑。
- `del_dev_plan.md`、`crypto_tool/dev_plan.md`、`crypto_tool/README.md`、`docs/experiment.md` 是舊版的開發計畫／實驗紀錄，保留原樣。
