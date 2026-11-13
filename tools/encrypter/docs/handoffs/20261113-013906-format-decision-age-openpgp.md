# Encrypter 0.4.0：格式決定（age＋OpenPGP）、整合結果、擁有者要跑的步驟

- **狀態：進行中**（2026-11-13）：整合完成在 `dev/encrypter`，**還沒合併回 master、還沒打包、還沒發版**。
  合併並發版後把這一行改成「已修」並寫上 merge commit 與 tag。
- 建立：2026-11-13 ｜ 範圍：`tools/encrypter/`，以及 hub 的 `README.md`（工具表一列）、`docs/HANDOFF.html`、`docs/OPEN_ISSUES.md`、`.env.example`
- 開發線：`dev/encrypter`
- 前提：同資料夾 `20261112-2210xx`～`2214xx` 五張設計稿與 `20261112-223325-encrypter-intent-and-redesign.md`（這張裁決了它們之間的不一致）
- **寫給接手的 agent**：先讀這張，再讀工具 README（用法、萬用鎖、多層、交接）。下面「擁有者的步驟」照順序做就能合併、打包、發版。

## 需求（改寫，非原話）

這個 repo 是公開的，所以只放改寫後的需求：

- 把 Encrypter 整理到可以放心給別人下載使用、可以交接的穩定版。
- 同時要「PGP 模式」與一個簡單的預設模式；兩者都要能讓好幾個人各用自己的鑰匙開同一份檔，擁有者另有一把「萬用鎖」都打得開，
  而且檔案不能因此變好幾倍大。
- 要能一層一層包（每層可以夾帶旁邊的檔案），擁有者用萬用鎖一路解到底。
- 開發線上先後出現兩個都叫「ISD2」的東西，要消除這個混淆。

## 問題一句話

0.3.x 的格式是自己排的（沒有人審過、災難時只能靠這個工具），開發線上又有兩批互相矛盾的設計；要一次決定格式，
並把萬用鎖、多層、換鎖做成標準做法，而不是再發明一種格式。

## 脈絡

- 兩批 11/12 的文件不一致：設計稿建議公開的 age（Q1-A），另一個工作階段寫了自有格式 ISD2（64 bytes 檔頭，沒發版）。
  設計稿自己也定義了一個同名的「金鑰槽版 ISD2」（從沒實作）。
- 限制：不從網路安裝任何套件（只能用已在 requirements 的 `cryptography` 與系統 `gpg`）；不自創密碼學原語或格式；這台電腦不執行網路上抓來的程式。
- 平行完成的三條分支：`dev/encrypter-age`（age v1 核心，自寫，通過 C2SP CCTV 官方向量 128 個）、
  `dev/encrypter-pgp`（PGP 模式，呼叫 gpg，每次用暫時的 GNUPGHOME）、`research/master-lock`（萬用鎖研究與 MLOCK 原型）。
- age 規格規定：密語（scrypt）必須是檔案裡唯一的鎖。所以「密語＋萬用鎖」只能用 OpenPGP。

## 決定

| 題目 | 選項 | 決定 |
|---|---|---|
| 加密檔格式（設計稿 Q1） | A 公開 age／B 自有金鑰槽格式／C 維持 ISD2 預覽格式 | **A 的變形（已採用）**：簡單模式＝age v1，用 `cryptography` 自寫實作（不加相依），另加 PGP 模式＝OpenPGP（系統 gpg）。不再產生任何自有格式 |
| 萬用鎖 | 自有金鑰槽格式（MLOCK）／標準多收件人 | **標準多收件人（已採用）**＋`rewrap`（換鎖）＋`rekey`（換檔案金鑰）。MLOCK 原型保留為研究參考，不打包 |
| 多層 | 一路加密成一個檔、看不出幾層／剝洋蔥（每層一個完整標準檔） | **剝洋蔥（已採用）**＋`decrypt --all-layers`。前者是靠隱藏換安全，不符合 Kerckhoffs 原則，也不更安全 |
| 兩個 ISD2 | — | 開發線上那個改稱「**ISD2 預覽格式（已停用）**」，只能解密；設計稿的金鑰槽版標示「**未採用**」 |
| 設定放哪 | 接 `libs/toolzoo/appdirs`／最小等效做法 | **最小等效做法**（`sealed/settings.py`，規則照抄 appdirs）：接 libs 要改 `tool.json` 的 pathex，之後每次改 libs 都得重打包 Encrypter；這裡只需要讀幾個鍵 |
| 設計稿 Q2～Q7 | — | 照建議（Q5 只做到「主視窗沒有舊演算法」，舊視窗仍能加密；Q7「找人審閱」列為下面要擁有者決定的事） |

## 做了什麼（`dev/encrypter`）

| commit | 內容 |
|---|---|
| `3759fcc` | Merge `dev/encrypter-age`（age 核心、CCTV 向量；向量檔合併後逐一比對 SHA256SUMS，128 個都沒被換行轉換改壞） |
| `c88098b` | Merge `dev/encrypter-pgp`（PGP 模式） |
| `8a1d5b5` | Merge `research/master-lock`（研究文件與原型） |
| `4cbb898` | fix：agefmt 在 `crypto_tool/` 為 sys.path 時也能載入（視窗程式與 `python <資料夾>` 的載入方式） |
| `06d32f2` | feat：`.env` 設定（萬用鎖公鑰、預設身分檔路徑），`.env.example` |
| `70e0a47` | feat：命令列（encrypt／decrypt／inspect／keygen／rewrap／rekey／--check、--all-layers、萬用鎖） |
| `bfbb915` | feat：新視窗（兩種模式、誰可以打開、萬用鎖、一路解到底、金鑰分頁） |
| `c122d77` | refactor：ISD2 預覽格式改成只能解密；tar 解包另外拒絕 Windows 保留名稱 |
| `fc34c1a` | fix：自己審閱後的兩個修正（一路解到底換名失敗時不中斷、視窗解 ISD2 預覽檔時挑對金鑰檔） |
| `09b169a` | chore：版本 0.4.0（`scripts/bump-version.ps1 encrypter minor`） |
| 之後的 docs commit | 工具 README、本張、其他交接單狀態、`docs/ui-spec.md`、`docs/legacy-modes.md`、研究文件頂端、hub 的 README／HANDOFF.html／OPEN_ISSUES.md |

合併進來的分支裡有 `test(encrypter): …` 標題的 commit（`dev/encrypter-age` 兩個、`dev/encrypter-pgp` 兩個），AGENTS.md 的 commit 類型沒有 `test`；
**沒有改寫歷史**，記在這裡。

## 驗證（2026-11-13，這台電腦）

- 環境：另一個已經裝好 `cryptography` 的 Python 環境（Python 3.11.9、cryptography 50.0.2），沒有 pycryptodome、ttkbootstrap、PyInstaller；系統有 Git for Windows 附的 GnuPG 2.4.9。
- 指令：`python -m unittest discover -s tools\encrypter\tests -v`
- 結果：**225 個，221 過**；2 個錯誤＝`test_mixture_modes`、`test_xorfold` 因缺 pycryptodome 匯入失敗（一直如此）；
  2 個略過＝外部 CCTV 資料夾沒設（`ENCRYPTER_CCTV_AGE_DIR`）、舊格式測試缺 pycryptodome。約 2 分鐘（PGP 測試實際呼叫 gpg）。
- 命令列測試涵蓋：每個指令的成功與失敗 `--json`、退出碼、祕密不出現在任何輸出、三層洋蔥＋萬用鎖一路解開、只有中間一層鑰匙時停在正確的層、
  rewrap 後舊鑰匙失效而萬用鎖仍可且內容位元組不變、rekey、ISD2 預覽檔仍解得開但程式庫與命令列都沒有產生它的方法、PGP 模式（金鑰對、多收件人＋萬用鎖＋密語、rekey）。

## 擁有者的步驟（在有網路、可以跳視窗的電腦上，照順序）

這台電腦**不能**跑 `scripts\build.ps1 encrypter`：它會建立 `tools\encrypter\.venv` 並從網路 `pip install`。

```powershell
# 0. 到 PersonalToolZoo 的主資料夾（master）。master 上目前有別人沒 commit 的修改：先 commit 或 stash，確認乾淨
git status
git switch master

# 1. 合併（一定要 --no-ff）
git merge --no-ff dev/encrypter -m "Merge dev/encrypter: Encrypter 0.4.0 - age and OpenPGP only, master lock, all-layers" -m "只產生公開格式（age 自寫實作、OpenPGP 呼叫 gpg）；萬用鎖＝多收件人、rewrap／rekey、decrypt --all-layers；新命令列與視窗；ISD2 預覽格式改唯讀。驗證見 tools/encrypter/docs/handoffs/20261113-013906-format-decision-age-openpgp.md。"
#    預期衝突（兩邊都改了這三份總覽）：
#      README.md            工具表：其他工具的列用 master 的；Encrypter 那一列用 dev/encrypter 的
#      docs/HANDOFF.html    其他工具、總表、時間線用 master 的；Encrypter 的總表列、工具卡、11/13 時間線用 dev/encrypter 的
#      docs/OPEN_ISSUES.md  兩邊的條目都留；Encrypter 那一條用 dev/encrypter 的
#    解完：
git add README.md docs/HANDOFF.html docs/OPEN_ISSUES.md
git commit --no-edit

# 2. 打包＋冒煙測試（建 .venv、從網路裝套件、打包、把 exe 開 10 秒：桌面會跳出視窗）
$env:TOOLZOO_NO_BROWSER = 1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\build.ps1 encrypter
#    結果表要是 OK；產物 dist\encrypter\GUI__Encrypter(v0.4.0).exe

# 3. 用工具自己的環境跑全部測試（這次有 pycryptodome，舊的也會跑；預期全部通過）
.\tools\encrypter\.venv\Scripts\python.exe -m unittest discover -s tools\encrypter\tests -v
.\tools\encrypter\.venv\Scripts\python.exe tools\encrypter\crypto_tool --check --json

# 4. 打開打包後的 exe（或 .\tools\encrypter\run.bat），照 tools\encrypter\docs\ui-spec.md 最後的「驗收清單」逐項看
```

**打包後的 exe 沒有主控台**：雙擊是視窗；命令列一律走原始碼（`.\tools\encrypter\.venv\Scripts\python.exe tools\encrypter\crypto_tool <指令>`）。

```powershell
# 5. 互通交叉測試：在一台裝了 age（或 rage）的電腦，在 repo 根目錄
function ct { & .\tools\encrypter\.venv\Scripts\python.exe tools\encrypter\crypto_tool @args }
#    每一項都比對 Get-FileHash 相同
Set-Content sample.txt "cross test 1"
ct keygen -o t.key                                   # 記下印出的 age1…（下面寫成 <T>）
ct encrypt sample.txt -o a.age -r <T>
age -d -i t.key -o a.out a.age                           # 本工具 → age（二進位）
ct encrypt sample.txt -o b.age -r <T> --armor
age -d -i t.key -o b.out b.age                           # 本工具 → age（文字形式）
ct encrypt sample.txt -o c.age --passphrase
age -d -o c.out c.age                                    # 本工具 → age（密語）
ct keygen -o locked.key --protect
ct encrypt sample.txt -o d.age -r <locked.key 的公鑰>
age -d -i locked.key -o d.out d.age                      # 密語保護的身分檔 age 也認得
age-keygen -o g.key                                      # 記下公鑰 <G>
age -r <G> -r <T> -o e.age sample.txt
ct decrypt e.age -o e.out -i g.key                    # age → 本工具（多收件人，用任一把）
ct decrypt e.age -o e2.out -i t.key
age -a -r <T> -o f.age sample.txt
ct decrypt f.age -o f.out -i t.key                    # age 文字形式 → 本工具
age -p -o h.age sample.txt
ct decrypt h.age -o h.out --passphrase                # age 密語 → 本工具
ct rewrap a.age -o i.age -i t.key -r <G>
age -d -i g.key -o i.out i.age                           # 換鎖後 age 也解得開
#    （rage 的指令相同：rage -d -i … ／ rage -r … ／ rage-keygen）
#    PGP 模式另外可在有 Gpg4win／Kleopatra 的電腦試：本工具加密的 .gpg 用 Kleopatra 解、Kleopatra 加密的檔用本工具解
#    任何一項不一致：不要發版，把那一項的指令與錯誤訊息記到新的交接單

# 6. 發版（版本已經是 0.4.0，用 keep：不改版號、清快取重 build＋冒煙測試、打 tag Encrypter_v0.4.0；不會產生 release commit）
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\release.ps1 encrypter keep -Yes

# 7. 推上 GitHub（連同開發線與 tag）
git push origin master dev/encrypter --follow-tags
```

合併並發版後：把這張與工具 README「現況」改成已發版、寫上 merge commit 與 tag；`docs/OPEN_ISSUES.md` 的 Encrypter 條目移到「已解決」。

## 沒有驗證的事

- **畫面沒有人實際看過**（只在假的 tkinter 上跑過整個視圖）。
- **沒有和真的 age／rage 交叉測試**；age 實作只有官方向量與自己的負向測試，**沒有外部審閱**。
- `tools\encrypter\.venv`、`build.ps1 enc`、打包後的 exe 都沒跑過（這台不能從網路裝套件）。
- Gpg4win（原生版 gpg）沒有實測；只在 Git for Windows 附的 GnuPG 2.4.9 上跑過。
- 大檔記憶體只量到 55 MiB（峰值約 0.5 MiB，不隨大小成長）；更大的檔沒量。
- 舊格式（`.isd`、Mixture）的 7 個測試這一輪沒跑（缺 pycryptodome）；程式沒有動到它們。

## 需要擁有者決定的事（都有預設，不回答就照預設）

| # | 題目 | 選項 | 建議（預設） |
|---|---|---|---|
| D1 | age 實作要不要找有密碼學經驗的人審閱 | A 要，審閱前標示「未審閱」、重要資料留原檔／B 不找，靠官方向量＋第 5 步的交叉測試 | **A**（預設：在審閱之前 README 維持「尚未經外部審閱」的標示） |
| D2 | 要不要做簽章（證明是誰做的、沒被換掉） | A 這一版不做／B 下一版用 gpg 加簽章 | **A**，有需要再做 B |
| D3 | 萬用鎖私鑰怎麼保管 | A 密語保護的身分檔放在平常不插的隨身碟＋紙本兩份／B 只放密碼管理器／C 放在這台電腦 | **A**（C 不建議：電腦出事時一起不見） |
| D4 | `--key-env`（ISD2 預覽格式用）要不要拿掉 | A 0.5 拿掉／B 一直留著 | **A**（ISD2 預覽格式從沒發版，0.5 時應該沒有檔案要解了） |
| D5 | 舊視窗還能「加密」 | A 改成只能解密（要動舊程式）／B 維持 | **B**（照「舊程式不刪不改」；主視窗已經沒有舊選項） |
| D6 | 命令列要不要另出一個有主控台的 exe | A 不出，命令列走原始碼／B 另出 | **A** |

## 驗收（這張本身）

- [x] 三條分支用 `--no-ff` 合進 `dev/encrypter`，merge commit 訊息寫明做了什麼、為什麼。
- [x] 命令列與視窗都能用兩種模式加密／解密、產生金鑰、處理資料夾；萬用鎖、rewrap、rekey、--all-layers 有測試。
- [x] ISD2 預覽格式只能解密；兩個 ISD2 的名字在文件裡分清楚。
- [x] 版本 0.4.0 用 repo 腳本改。
- [ ] 擁有者的步驟 1～7 做完（合併、打包、測試、看畫面、交叉測試、發版、push）。
- [ ] D1～D6 有答案或確認照預設。

## 不要做的事

- 不要在這台電腦跑 `build.ps1 encrypter` 或任何會 `pip install` 的東西；不要執行網路上抓來的 age／rage。
- 不要再發明格式或「混合」加密；萬用鎖與多層都用 age／OpenPGP 現成的做法。
- 不要讓密語能放在命令列參數；不要在任何輸出、錯誤、`.env` 裡放私鑰或密語。
- 不要動 `core/`、`gui/tab_*.py`、`gui/widgets.py`（舊檔靠它們解）；不要把 `prototype/master_lock/` 接進工具。
- 交叉測試沒過之前不要發版；不要 fast-forward 合併。

## 收尾紀錄

（合併、發版後補：日期、merge commit、tag、交叉測試結果、略過的驗證。）
