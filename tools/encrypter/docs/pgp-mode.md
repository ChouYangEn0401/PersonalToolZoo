# PGP 模式（`crypto_tool/pgpmode/`）

PGP 模式呼叫系統上的 `gpg` 執行檔（GnuPG 2.2 以上），產生與解開**標準 OpenPGP** 檔案
（二進位 `.gpg`、文字 `.asc`）。任何裝了 GnuPG、Kleopatra、Sequoia、OpenPGP.js 等 OpenPGP 程式的電腦
都能解開，不需要這個工具。

> 跟 `crypto_tool/core/pgp.py` 無關：那是舊版的實驗程式，**不是** OpenPGP 格式，保留不動。

## 能做什麼

| 功能 | 說明 |
|---|---|
| 多收件人（萬用鎖） | 同一份密文，任一把收件人的私鑰都能解開。內容只加密一次，每多一把鎖只多一個幾百位元組的封包 |
| 收件人＋密語並存 | 同一份密文，可以用私鑰開，也可以用密語開 |
| 產生金鑰 | 公鑰、私鑰各匯出成 ASCII armor 檔；私鑰可以有或沒有密語（沒有時回傳值與檔案都會標示） |
| 看資訊 | 不需要金鑰：armor 與否、收件人 key ID、有沒有密語封包、資料封包種類 |

## 公開 API

```python
from crypto_tool import pgpmode

pgpmode.find_gpg(*, refresh=False) -> GpgInfo          # path, version, msys, gpgconf, source
pgpmode.is_pgp(head_bytes) -> bool                     # 二進位封包與 armor 都認得
pgpmode.pgp_kind(head_bytes) -> str | None             # "message" / "public_key" / "secret_key" / "signature" / "signed_text"
pgpmode.generate_keypair(name, email=None, *, out_public, out_secret, passphrase=None,
                         overwrite=False, key_type="ed25519", out_revocation=None) -> dict
pgpmode.encrypt_file(src, dst, *, recipient_key_files=(), passphrase=None,
                     armor=False, overwrite=False) -> dict
pgpmode.decrypt_file(src, dst, *, secret_key_files=(), key_passphrase=None,
                     passphrase=None, overwrite=False) -> dict
pgpmode.inspect(path) -> dict
```

- `generate_keypair` 回傳 `fingerprint`、`uid`、`public_key`、`secret_key`、`protected`（私鑰有沒有密語，
  由實際封包判斷），沒有密語時另有 `warning`，私鑰檔也多一行 `Comment: WARNING: this secret key is NOT protected by a passphrase`。
  `key_type` 可選 `ed25519`（預設，主金鑰 Ed25519＋加密子金鑰 Curve25519）、`rsa3072`、`rsa4096`。
- `decrypt_file` 可以只給私鑰、只給密語，或兩者都給（先試私鑰、再試密語）。回傳的 `used` 是 `key` 或 `passphrase`。
- 錯誤一律是 `crypto_tool.sealed.errors.SealError`，只用既有代碼：

| 代碼 | 什麼時候 |
|---|---|
| `dependency_missing` | 找不到 gpg、版本低於 2.2、`ENCRYPTER_GPG` 指錯 |
| `bad_input` | 沒給收件人也沒給密語、密語有換行、名稱或信箱格式不對、輸入是資料夾 |
| `input_missing` | 輸入檔或輸出資料夾不存在 |
| `output_exists` | 輸出檔（或金鑰檔）已存在且沒要求覆蓋 |
| `key_missing` | 金鑰檔不存在 |
| `bad_key_format` | 金鑰檔不是 OpenPGP 金鑰、把公鑰當私鑰給、收件人公鑰不能加密（過期、撤銷、沒有加密子金鑰） |
| `unsupported_format` | 不是 OpenPGP 檔、給的是金鑰而不是加密檔、沒有完整性保護的舊式加密檔、沒加密的訊息 |
| `wrong_key` | 私鑰不是收件人、私鑰密語不對、檔案密語不對 |
| `corrupt` | 完整性檢查沒通過（被改過）、截斷、封包壞掉 |
| `io_error` | 讀寫失敗、gpg 逾時、找不到能放暫存 home 的地方 |

`detail` 只放 gpg 狀態關鍵字與 stderr 最後幾行的摘要（會先把呼叫端給的密語換成 `***`），
不放密語、私鑰內容、明文。

## 怎麼找 gpg

依序：

1. 環境變數 `ENCRYPTER_GPG`（gpg 執行檔的完整路徑）。有設但不能用時直接報錯，不會偷偷換別的。
2. `PATH` 上的 `gpg`。
3. 常見位置：Gpg4win 的 `%ProgramFiles(x86)%\GnuPG\bin`、`%ProgramFiles%\GnuPG\bin`，
   Git for Windows 的 `%ProgramFiles%\Git\usr\bin`、只裝給自己的 `%LOCALAPPDATA%\Programs\Git\usr\bin`
   （Linux／macOS 看 `/usr/bin`、`/usr/local/bin`、`/opt/homebrew/bin`）。

每個候選跑一次 `gpg --homedir /nonexistent/encrypter-gpg-probe --version`（指定一個不存在、gpg 也不會建立的 home，
所以連探測都不碰預設金鑰環），版本低於 2.2 的略過。**MSYS 版**的判斷：同資料夾有 `msys-2.0.dll`，
或 `--version` 的 `Home:` 行是 `/` 開頭。結果依（`ENCRYPTER_GPG`, `PATH`）快取。

Git for Windows 的 gpg 通常**不在** PowerShell 的 PATH 上（只有 Git Bash 裡有），所以第 3 步很重要。

## 暫時的專用 GNUPGHOME

**每一次操作**（產生金鑰、加密、解密、看資訊）都開一個新的、名字隨機的 home，用完就刪：

- 每個 gpg／gpgconf 呼叫都明確帶 `--homedir <暫時 home>`，子行程環境的 `GNUPGHOME` 也設成同一個，
  並清掉 `GPG_AGENT_INFO`、`GPG_TTY`。使用者自己的金鑰環（`%APPDATA%\gnupg`、`~/.gnupg`）
  不使用、不讀取、不修改；測試會確認每一個呼叫都帶暫時 home，且預設金鑰環的檔案在測試前後完全一樣。
- 結束時（`finally`）先 `gpgconf --homedir <同一個 home> --kill all` 關掉這個 home 的 gpg-agent
  （原生版另外 `--remove-socketdir`），再刪資料夾；Windows 上檔案可能短暫被鎖住，所以刪除會重試幾次。
  沒刪成功的資料夾帶有 `.encrypter-gpg-home` 記號，之後的操作會把超過一天的清掉。

### 放在哪

依序取第一個「路徑夠短而且能寫入」的上層資料夾，底下開 8 個十六進位字元的子資料夾：

1. 環境變數 `ENCRYPTER_GPG_TMPDIR`（有設時）。
2. 工具的 `data/g/`：從原始碼執行是 `tools/encrypter/data/g/`（`.gitignore` 已擋 `tools/*/data/`），
   打包的 exe 是 exe 旁邊的 `data/g/`；有設 `TOOLZOO_DATA_DIR` 時是 `<TOOLZOO_DATA_DIR>/encrypter/g/`。
   這跟 `libs/toolzoo/appdirs.tool_data_dir("encrypter")` 同一個位置（Encrypter 不依賴 `libs`，所以照抄規則）。
3. 系統暫存資料夾的 `egpg/`。

**理由。** repo 規則是執行時資料放工具的 `data/`、不要用 `%TEMP%` 存東西，所以預設用 2。
但 gpg-agent 的 socket 路徑有長度上限：Unix socket（含 MSYS 的模擬）最多 107 個字元，
最長的 socket 名稱是 `S.gpg-agent.browser`，所以 home 路徑最多 87 個字元
（實測：路徑太長時 agent 直接報 `socket name ... is too long` 起不來）。
**而且長度本身會影響能不能解密：home 一律補成指定長度，用私鑰的操作失敗時換長度重來。** 實測 Git for Windows 的 GnuPG 2.4.9，
匯入**沒有密語保護**的 Curve25519 私鑰後第一次使用，會不會「Bad secret key」取決於 home 參數（`/c/…` 形式）的
長度、金鑰本身、同一次匯入了哪幾把；同一個 home 裡重試也不會好，換一個長度的 home 通常就好（2026-11-13，5 把金鑰 × 長度 43～86）：

| home 長度 | 結果 |
|---|---|
| 43～54 | 有的金鑰壞（各在不同的長度） |
| 55～74 | 單把匯入時 5 把都正常；長度 64、72 另外各連續產生 10 把也都正常。但「兩把一起匯入」在 64 遇過必壞、在 55 正常 |
| 75 以上 | 大多數壞 |

做法：
- `make_home` 把隨機資料夾名稱補長，讓整個 home 參數剛好是指定長度（預設 `HOME_LEN = 64`）；
  上層資料夾本身太長（補不出至少 8 個字元的名稱）就換下一個候選。
- 需要私鑰的兩個地方（產生金鑰後的自我檢查、解密）走 `ops._session_with_keys`：匯入後用一小段測試資料把每把私鑰實際用一次，
  有私鑰轉換失敗就關掉這個 home，換 `HOME_LEN_CHOICES = (64, 55, 70, 60, 58, 67)` 的下一個長度重來；
  每個 home 裡最多重試 4 次（處理真正偶發的情況）。全部試完還失敗，才照實回報 Bad secret key。
  有密語的私鑰，同一個問題有時會報成「Bad passphrase」（產生金鑰後用剛設好的密語自我檢查也遇過），所以這種也換 home 重試；
  代價是密語真的打錯時要多等幾秒才回報。
- 解密時就算暖身通過，真的解密偶爾還是會失敗，兩種樣子：
  - `Bad secret key`：同上的轉換問題。
  - `Bad session key`：檔案**同時有密語封包**時，gpg 會先用 passphrase-fd 的值試密語封包（私鑰沒有密語時，工具給一個隨機的假密語，
    讓它失敗後改用私鑰）。錯的密語解開密語封包裡加密的工作階段金鑰，得到的是亂碼，但大約 1% 的機會第一個位元組剛好是合法的演算法代號，
    gpg 就拿這個亂碼去解內容而失敗，不再試私鑰；同一個假密語每次都一樣。
  兩種都整個換一個起始長度不同的 home、並換一個新的假密語重解，最多 3 次；真的不是收件人時也會多試這幾次才回報。
  **還沒解決的情況**：私鑰本身有密語保護時，假密語就是私鑰的密語（gpg 的 passphrase-fd 只有一個值），沒辦法換；
  這種檔案大約 1% 會固定解不開，改用檔案密語解，或用沒有密語保護的私鑰（或先在別的 OpenPGP 程式解）。
- Gpg4win（原生版）沒有實測，一樣照這個做，不會有壞處。
工具放在很深的資料夾時 2 會超過，這時才退到 3。3 只放**用完即刪**的暫存，不是長期存東西，
而且系統暫存資料夾通常比工具資料夾短、也不會被雲端硬碟同步。

### MSYS 版要轉路徑

Git for Windows 附的 gpg 是 MSYS 程式：`GNUPGHOME=C:\Users\...`（或 `C:/Users/...`）會被當成**相對路徑**，
找不到資料夾、agent 起不來。所以 MSYS 版的 `--homedir`／`GNUPGHOME` 一律轉成 `/c/Users/...` 形式；
輸入、輸出檔案的引數用 Windows 路徑就可以（實測含中文與空白的路徑也正常）。

## 固定的 gpg 參數

```text
--homedir <暫時 home> --batch --no-tty --pinentry-mode loopback
--trust-model always --no-auto-check-trustdb
--disable-dirmngr --no-auto-key-retrieve --no-auto-key-locate     # 不連網路、不啟動 dirmngr
--no-greeting --no-permission-warning
--utf8-strings --display-charset utf-8                            # 中文 uid 不會變亂碼
--keyid-format long --status-fd 1
--no-symkey-cache                                                 # 2.2.7 以上：密語不留在 agent 快取
```

- **密語只走 `--passphrase-fd 0`**（stdin 管線），永遠不放在命令列引數或環境變數。測試會攔下每個子行程的
  argv 與環境，確認特徵明顯的假密語從沒出現過。
- `subprocess` 不用 shell；逾時 120 秒＋每 4 MiB 加 1 秒；Windows 上用 `CREATE_NO_WINDOW` 不跳主控台視窗。
- 解密加 `--skip-verify`：這一版只管加密，不驗簽章（有簽章的檔案照樣解得開，但不告訴你是誰簽的）。

## 互通性的選擇與證據

**問題。** GnuPG 2.4 在 `--compliance=gnupg`（上游的預設）下產生的金鑰會宣告 AEAD（LibrePGP 的 OCB），
別人用 GnuPG 2.4 加密給這種金鑰時，會產生 tag 20 的「AEAD encrypted data」封包——這種封包只有 GnuPG 2.3 以上
與少數 LibrePGP 實作讀得懂，GnuPG 2.2 以及只實作 RFC 9580 的程式（例如 Sequoia）都解不開。

**實測（Git for Windows 附的 GnuPG 2.4.9，`gpg --list-packets`）：**

| 做法 | 金鑰的 features／偏好 | 加密出來的資料封包 |
|---|---|---|
| 產生金鑰時 `--compliance=gnupg --rfc4880bis` | `features: 07`、`pref-aead-algos: 2`（OCB） | — |
| 加密給上面那把金鑰，`--compliance=gnupg` | — | `:aead encrypted packet: cipher=9 aead=2 cb=16`（tag 20） |
| 加密給同一把金鑰，`--force-aead` | — | tag 20（OCB） |
| 加密給同一把金鑰，`--compliance=openpgp` | — | `:encrypted data packet:`、`mdc_method: 2`（tag 18，SEIPD v1＋MDC） |
| 產生金鑰時 `--compliance=openpgp` | `features: 01`（只有 MDC），沒有 `pref-aead-algos` | — |
| 只用密語（`-c`），`--compliance=openpgp` | — | SKESK v4（`aead 0`）＋SEIPD v1 |

（這個 Git for Windows 版本不加任何參數時本來就不宣告 AEAD，但 Gpg4win 等上游版本的預設是 `gnupg`，
所以不能靠預設值。）

**決定。**

1. 加密一律 `--compliance=openpgp`（RFC 4880 行為：SEIPD v1＋MDC，絕不產生 AEAD 封包），
   並 `--personal-cipher-preferences "AES256 AES192 AES"`。即使收件人的金鑰宣告 AEAD 也一樣（有測試）。
2. 產生金鑰也用 `--compliance=openpgp`：金鑰只宣告 `features: 01`、沒有 AEAD 偏好，
   所以**別人**用 GnuPG 2.4 加密給這把金鑰時也會產生 SEIPD v1。自我檢查會再確認一次。
3. 加密完再用 `--list-packets` 檢查一次，資料封包不是 SEIPD v1 就放棄輸出（防止全域設定強制 AEAD）。
4. 解密不限制：gpg 讀得懂的（包含別人給的 OCB 檔）都解，但一定要通過完整性檢查。
   沒有完整性保護的舊式 SED 封包（tag 9）拒絕解。
5. 金鑰演算法預設 Ed25519＋Curve25519（v4 金鑰）：GnuPG 2.1 以上、OpenPGP.js、Sequoia、GopenPGP、
   BouncyCastle、RNP 都支援。要給很舊的程式（GnuPG 1.4／2.0、舊版 PGP Desktop）用時選 `rsa3072`／`rsa4096`。

SEIPD v1 是 RFC 4880 與 RFC 9580 都要求支援的格式，所以這是目前「能被最多 OpenPGP 實作解開」的選擇。

## 怎麼判斷解密成功

輸出先寫到目標旁邊的 `.<檔名>.partial-xxxx`，**gpg 退出碼 0、狀態行有 `DECRYPTION_OKAY`，
而且有 `GOODMDC`（或是 AEAD 封包）、沒有 `BADMDC`／`DECRYPTION_FAILED`** 才改名成目標；
其他情況一律刪掉暫存檔。gpg 失敗時會留下寫了一半的輸出檔（實測），所以這一步不能省。

用狀態行（`--status-fd`）分類，不看人話訊息：

| 狀態 | 結果 |
|---|---|
| `BADMDC` | `corrupt`（被改過） |
| `DECRYPTION_INFO 0 …` 且不是 AEAD | `unsupported_format`（沒有完整性保護） |
| `ERROR pkdecrypt_failed …11`（Bad passphrase）／`177`（No passphrase）、`NEED_PASSPHRASE` | `wrong_key`（私鑰密語） |
| `NO_SECKEY`、沒有 `DECRYPTION_KEY` | `wrong_key`（私鑰不是收件人） |
| `NEED_PASSPHRASE_SYM` 後 `ERROR symkey_decrypt.maybe_error 11_BAD_PASSPHRASE` | `wrong_key`（檔案密語） |
| 拿到工作階段金鑰後 `DECRYPTION_FAILED`、或連收件人封包都沒處理就失敗 | `corrupt`（截斷） |
| 退出碼 0 但沒有 `BEGIN_DECRYPTION` | `unsupported_format`（沒加密的訊息） |

同時給私鑰與密語時分兩次執行（各用一個新的暫時 home）：gpg 的 `--passphrase-fd` 一次只能給一個值，
而且檔案有密語封包時 gpg 會先拿這個值去試密語封包。私鑰沒有密語時會給一個隨機的假值，
因為給空字串時 gpg 試完密語封包就直接放棄、不再試私鑰（實測）。

## 已知限制與注意事項

- **Curve25519 私鑰匯入後偶發失敗（GnuPG 的問題）。** 實測 Git for Windows 的 GnuPG 2.4.9（libgcrypt 1.12）
  在新的 home 匯入 Curve25519 私鑰後，第一次使用時常報 `Bad secret key`（有密語的私鑰偶爾報 `Bad passphrase`），
  同一把私鑰重試幾次就會成功，成功後就一直正常；RSA、NIST P-256 沒有這個問題。
  所以匯入私鑰後會先用一小段測試資料把每把私鑰解一次（最多 12 次；「密語不對」連續 3 次才算真的不對），
  再解真正的檔案。這讓解密多花約 1～3 秒；密語打錯時要多等幾秒才回報。
- 一次處理一個一般檔案；資料夾與多個檔案要先打包（由呼叫端處理）。
- 不驗簽章、不簽章。
- 隱藏收件人（`--throw-keyids` 產生的檔）`inspect` 會回報 `hidden_recipients`，解密時 gpg 會逐一試給的私鑰。
- 撤銷憑證預設不另存；需要時給 `out_revocation`。
- 暫時 home 在操作期間會有匯入的私鑰（沒有密語的私鑰是明文），操作結束就刪。
- 只在 Git for Windows 的 MSYS 版 GnuPG 2.4.9 上實測過。Gpg4win（原生版）照文件應該一樣能用
  （原生版不需要轉路徑，socket 可能放在 `%LOCALAPPDATA%\gnupg\d.*`，所以結束時多跑 `--remove-socketdir`），
  但這台電腦沒有裝，沒有實測。

## 測試

```powershell
# 在 repo 根目錄
python -m unittest discover -s tools\encrypter\tests -p "test_pgpmode_*.py" -v
```

- `test_pgpmode_unit.py`：不需要 gpg（格式辨識、路徑轉換、找不到 gpg 的降級訊息、密語只走 stdin）。
- `test_pgpmode_gpg.py`：實際呼叫 gpg，找不到 gpg 時整組略過。金鑰在測試開始時產生（uid 用 `example.invalid`），
  全部離線，大約兩分鐘。另外檢查：每個 gpg 呼叫都帶暫時 home、預設金鑰環前後不變、
  沒有殘留的暫時 home 與屬於測試 home 的 gpg-agent、特徵明顯的假密語不出現在任何例外、回傳值與子行程引數。
