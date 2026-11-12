# 舊版功能（.isd 格式與 Mixture）：原本做什麼、為什麼下架、怎麼救回

v0.3.0 的功能從主視窗下架了，但**程式一行沒刪**，仍然可以用。這份文件記下三件事，之後誰想把它找回來都有依據。
完整的分析與選項在 `handoffs/20261112-223325-encrypter-intent-and-redesign.md`。

## 在哪裡

| 東西 | 位置 | 現況 |
|---|---|---|
| 舊的四個分頁（File／Text／Mixture／Large File） | `crypto_tool/gui/tab_*.py`、`gui/widgets.py` | 沒動。從主視窗「關於 → 開啟舊版工具」打開 |
| 舊主視窗的外框 | `crypto_tool/gui/legacy_app.py`（原 `gui/app.py`） | 改成獨立視窗，最上面加警告 |
| 舊格式與演算法 | `crypto_tool/core/`（engine、pipeline、bytefile、pgp、utils） | 沒動 |
| PGP 示範視窗 | `crypto_tool/gui/pgp_demo.py` | 沒動（本來就不在主視窗裡） |
| 舊測試 | `tests/test_mixture_modes.py`、`tests/test_xorfold.py` | 沒動（需要 pycryptodome） |
| 舊文件 | `crypto_tool/README.md`、`crypto_tool/dev_plan.md`、`del_dev_plan.md`、`docs/experiment.md` | 沒動，檔頭加了一行指到這裡 |

## 原本做什麼

- **`.isd` 格式**：一個文字檔，`CONTENT="""<base64 的密文>"""` 加 `NOTE="""<JSON 說明>"""`。
- **十一種「演算法」**：AES-256-CBC（預設）、AES-256-GCM、ChaCha20-Poly1305、Blowfish-CBC、3DES-CBC、XOR、XOR-FOLD、
  Base64、PGP、PGP-Multi、PGP-Escrow。密碼用 PBKDF2-SHA256（十萬次）轉成金鑰；也可以拿任何檔案的雜湊當金鑰。
- **Mixture · All-In-One**（更早叫 Simple，再更早叫 Layered）：同一份資料連續加密好幾次，每次可以用不同的演算法與密碼，
  最後包成**一個** `.isd`。要全部的密碼、照同樣的順序才解得開。
- **Mixture · Layered**（更早叫 Node、Nested）：每加密一次就包成一個完整的 `.isd`，再把這個 `.isd` 當成下一次的輸入，
  像俄羅斯娃娃。解一次得到裡面那一層的 `.isd`，可以一層一層交給不同的人解。
- **PGP 系列**：隨機產生一把 AES 金鑰加密內容，再用每位收件人的 RSA 公鑰把這把金鑰包起來。
  名字叫 PGP，但不是 OpenPGP，跟 gpg 不相容。Escrow 就是多加一位「第三方」收件人。
- **Large File**：把大檔切成很多塊，每塊各自加密成一個 `.isd`，另外寫一份 `manifest.json`。介面上自己標了 UNTESTED。

## 為什麼下架

一句話：**兩種 Mixture 模式在加密上是同一件事，而且都不會比「用一個好的演算法加密一次」更安全；
同時舊格式缺了現代加密該有的「防竄改」。** 細節：

1. All-In-One 與 Layered 的差別只有「中間有沒有多包一層 base64 與 JSON」。兩者都是「加密再加密」。
   花了很多版在調的「解一次會看到什麼」，是包裝的差別，不是安全性的差別。
2. 疊很多層不會更安全。AES-256 一層就足夠；真正的弱點是密碼好不好猜，疊十層也補不了一個好猜的密碼。
   「同一個密碼加密 N 次」（File 分頁的 Iterations）完全沒有增加強度。
3. 預設的 AES-256-CBC 沒有完整性驗證：密文被改過，解密不一定會發現。「密碼打錯」是靠解出來的結尾格式不對才知道的，
   所以偶爾會把錯的密碼當成對的、吐出一堆亂碼。
4. `NOTE` 整段是明文而且沒有受保護：檔名、大小、作者、密碼提示、用了哪些演算法都看得到，也都可以被改。
5. 選單裡有幾個其實沒有保護力的選項跟 AES 排在一起：Base64 不是加密；XOR 是 32 bytes 的金鑰重複使用，
   知道一小段原文就能解；**XOR-FOLD 只會改到資料的前 32 個 bytes，後面全部是原文**。
6. 模式的名字換過三輪，而且互相撞名：「Layered」在舊版指「全部融合成一個」，在新版指「一層一層包」。
   文件各說各話，舊檔的 `mode` 欄位也因此可能被讀成相反的意思。
7. 整個檔案讀進記憶體、每一層再膨脹三分之一（base64），大檔與多層都很吃力；Large File 是另外寫的一套，沒有共用邏輯，
   `manifest.json` 也沒有保護（塊被調換、被抽掉不會發現）。

## 現在用什麼取代

新格式 **ISD2**（`crypto_tool/sealed/`）：AES-256-GCM 或 ChaCha20-Poly1305，密語用 scrypt，分塊加密，
檔頭與每一塊都經過驗證。資料夾、大檔、命令列都是同一套。見 `tools/encrypter/README.md`。

## 怎麼救回

- **只是要解舊檔**：主視窗「關於 → 開啟舊版工具」，照以前的方式解。
- **想把舊視窗變回主視窗**：在 `crypto_tool/GUI__Encrypter.py` 的 `main()` 裡不要建立 `CryptoToolApp`，
  改成建一個 `TkinterDnD.Tk()`、`ttk.Style(theme="darkly")`、呼叫 `legacy_app.apply_gold_overrides(style)`，
  再把 `legacy_app.open_legacy_window(root)` 裡的分頁放進去（或直接把 `gui/legacy_app.py` 還原成原本的 `gui/app.py`）。
- **要一模一樣的 v0.3.0**：`git checkout Encrypter_v0.3.0 -- tools/encrypter`（或只取 `crypto_tool/gui/app.py`）。
- **想把某個想法做成正式功能**（多把鑰匙缺一不可、多人各自能解、分段授權）：不要從舊程式改，
  照交接單「選項表」裡寫的標準做法，在 ISD2 上加。

## 建議

手上還有重要的舊 `.isd` 檔的話：用舊版工具解開，再用新格式重新加密一次，之後就不必再依賴舊版工具。
