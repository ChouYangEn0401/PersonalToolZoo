# 🔐 CryptoTool Pro

一款功能強大的加密/解密桌面工具，支援多種加密演算法、專屬 `.isd` 格式（輸出副檔名）、多階段混合加密，以及大檔案分段處理。

> **v1.4.0** 全面重構：Mixture Pipeline 核心拆出至 `core/pipeline.py`（File/Mixture/LargeFile 共用）、Mixture 模式更名（All-In-One→**All-In-One**、Layered→**Layered**）、加解密順序明確為 1→N 加密 / N→1 解密、Layered 每次只剝一層（修正 Mixture 多密碼 wrong padding 問題）、Mixture 支援文字模式 inline 結果顯示、Pipeline 階段支援 ↑↓ 換序、Mixture 完整支援 PGP / PGP-Multi / PGP-Escrow

---

## 功能特色

| 功能 | 說明 |
|------|------|
| **檔案加密 (Tab 1)** | 加密任意檔案為 `.isd`；支援 PGP/Multi/Escrow；Layered 每次解一層 |
| **文字加密 (Tab 2)** | 快速加密一段文字，支援 Base64 顯示、剪貼簿複製、存檔 |
| **混合加密 (Tab 3)** | 進階多階段加密管線，每階段可選不同演算法與密碼；支援 PGP/Multi/Escrow；↑↓ 換序；文字模式 inline 結果 |
| **大檔案模式 (Tab 4)** | 分段切割大檔案，逐段加密，產出 manifest + chunk 檔案 |
| **拖拉支援** | 所有檔案路徑輸入欄均可直接拖拉檔案（支援含空格、中文路徑）|
| **Tooltip 提示** | 滑鼠懸停在各元件上可查看功能說明 |

### 支援的加密演算法

| 演算法 | 類型 | 說明 |
|--------|------|------|
| AES-256-CBC | 區塊加密 | **預設**，業界標準 |
| AES-256-GCM | 認證加密 | 附帶完整性驗證 |
| ChaCha20-Poly1305 | 串流加密 | 現代高效率演算法 |
| Blowfish-CBC | 區塊加密 | 經典對稱加密 |
| 3DES-CBC | 區塊加密 | 三重 DES，向下相容 |
| XOR | 串流 | 以 PBKDF2 衍生金鑰進行 XOR |
| XOR-FOLD | 串流 | 折疊金鑰的 XOR — 確保金鑰每個位元都參與加密 |
| Base64 | 編碼 | 僅編碼，非加密（無需密碼） |
| **PGP** | 非對稱包裝 | RSA-4096 + AES-GCM hybrid，單一收件人 |
| **PGP-Multi** | 非對稱包裝 | 多收件人 RSA，每位收件人都能獨立解密 |
| **PGP-Escrow** | 非對稱包裝 | 多收件人 + 第三方強制解密金鑰，`.isd` 標記為可信任第三方解鎖 |

### 密碼類型

| 類型 | 說明 | 大小限制 |
|------|------|----------|
| **text** | 文字密碼 | ≤ 1024 字元 |
| **file** | 任意檔案的 SHA-256 雜湊 | ≤ 100 MB |
| **image** | 圖片檔的 SHA-256 雜湊 | ≤ 50 MB |
| **video** | 影片檔的 SHA-256 雜湊 | ≤ 200 MB |
| **bytefile** | `.isd` 內容的 SHA-256 雜湊（key-type: 以已匯出的 .isd/.bytefile 內容做為金鑰來源） | ≤ 50 MB |
| **txtfile** | 純文字檔內容的 SHA-256 雜湊（自動去除尾端換行，避免不同編輯器產生不同金鑰） | ≤ 50 MB |

---

## 安裝

### 環境需求
- Python 3.10+
- Windows / macOS / Linux

### 安裝步驟

```bash
# 1. 進入專案目錄
cd crypto_tool

# 2. 安裝相依套件
pip install -r requirements.txt

# 3. 啟動程式
python main.py
```

### 相依套件
- `pycryptodome` — 加密演算法庫
- `ttkbootstrap` — 現代化 tkinter 主題
- `tkinterdnd2` — 拖拉支援

---

## 更新紀錄

### v1.4.0
- **加解密順序修正確認**：All-In-One 加密 #1→#N、解密 #N→#1；Layered 同理，outermost = 最後一個 stage
- **Layered 單層剝除（File Tab）**：File Tab 解密 layered 文件改為每次只剝一層，修正多密碼 Mixture 檔案出現 wrong padding 的問題；解完後若結果仍是 .isd，再次解密即可繼續剝層
- **Mixture Pipeline 全功能 PGP 支援**：PGP / PGP-Multi（多收件人 ＋ 按鈕） / PGP-Escrow 均可用於 Pipeline 的任一 Stage；`STAGE_ALGORITHMS` 現包含所有演算法
- **Mixture Pipeline ↑↓ 換序**：每個 Stage 右側新增 ↑ / ↓ 按鈕，可即時調整管線順序
- **Mixture 文字模式 inline 輸出**：選擇 Text 輸入模式後，加密/解密結果直接顯示在 Result 文字區；提供 📋 Copy / 💾 Save .isd / 💾 Save .txt / ↩ Use as Input（可鏈式操作）
- **Mixture 文字模式 DnD**：可將 .isd 檔案拖拉至輸入文字區，自動載入 .isd 內容（用於解密）
- **Mixture 模式更名**（v1.4.0 延續）：`"all-in-one"`（All-In-One）與 `"layered"`（Layered）為目前預設模式字串（向下相容）
- **核心架構**：`core/pipeline.py` 作為唯一 pipeline 邏輯出口；GUI 完全不含加密業務邏輯；Large File Tab 未來可直接引用

### v1.3.0
- **XOR-FOLD 演算法**：折疊金鑰 XOR，確保整條金鑰都被使用；AlgoBar 與 tooltip 均已加入
- **PGP / PGP-Multi / PGP-Escrow**：RSA-4096 + AES-GCM 非對稱包裝，所有 4 個分頁均支援
  - **PGP**：單一公鑰收件人；選取後顯示內層演算法選擇器與公鑰匯入面板
  - **PGP-Multi**：可加入多位收件人（＋ 按鈕），每人均可用自己的私鑰解密
  - **PGP-Escrow**：在 Multi 基礎上額外加入一把 Escrow 主金鑰，`.isd` NOTE 標記 `pgp_escrow: true`  - **內層演算法 "None"**：原始資料直接封入 PGP 信封，不套任何對稱加密（無需密碼）  - 解密側：拖入 `.isd` 後若偵測到 `pgp_mode`，自動顯示私鑰匯入列
  - 可透過 `EncryptionEngine.pgp_generate_keypair(bits=4096)` 取得 `(priv_pem, pub_pem)` 金鑰對
- **txtfile 金鑰正規化**：讀取純文字金鑰檔案時自動 `rstrip("\r\n")`，解決不同編輯器儲存換行不一致導致的解密失敗
- **解密側自動選金鑰類型**：`.isd` 內有 `reveal_key_type` 時，解密卡片自動切換對應的密碼類型

### v1.2.0
- **AlgoBar（演算法選擇器）**：Tab 1 Advanced Settings 的演算法選擇改為分段式按鈕 Bar，金色高亮已選、hover 時有暖金光暈效果
- **Advanced Settings 移入加密卡片**：現在位於 Encrypt 方框內的可折疊面板，不再佔用頁面底部空間
- **演算法可見性開關**：新增 "Reveal algorithm in metadata" 切換鈕（預設開啟）；關閉時演算法不寫入 NOTE，解密需手動選擇
- **解密卡片 — File Metadata 面板**：拖入 `.isd` 後自動解析並顯示演算法（附 auto-detected 標籤）、密碼提示、作者資訊
- **解密側 — 密碼提示自動顯示**：加密時設定的 hint 在解密側自動顯示，金色突出
- **解密側 — 演算法隱藏警示**：若演算法被隱藏，顯示琥珀色警示並展開手動演算法選擇 Bar

### v1.1.0
- **拖拉支援**：Tab 1–4 中所有檔案/目錄輸入欄均可拖放檔案；含中文、空格的 Unicode 路徑均支援
- **Text Tab 拖拉**：可將 `.isd`（或舊有 `.bytefile`）或文字檔直接拖放到輸入文字框自動載入
- **Mixture Tab 拖拉**：可將金鑰檔案拖放到密碼欄，自動切換 Key type 為 `file`
- **暖金色主題**：視窗主題改為暗底金色點綴，Labelframe 標題金色、加密按鈕改為琥珀色
- **Tooltip 提示**：所有關鍵元件（演算法選擇、密碼欄、迭代次數、拖拉提示等）加入懸浮說明
- **編碼容錯**：文字檔載入自動 UTF-8 → latin-1 fallback，避免非 UTF-8 檔案崩潰

### v1.0.0
- 初始版本：四分頁加密工具，支援 7 種演算法與 5 種金鑰類型

---

## 使用教學

### Tab 1 — 檔案加密 / 解密

**加密檔案：**
1. 在左側「Encrypt」區塊點選 **Browse**（或拖拉檔案）選擇來源檔案
2. 輸入密碼（或切換密碼類型選擇檔案作為金鑰）
3. 展開 **Advanced Settings** 進行進階設定：
   - **Algorithm Bar**：點選欲使用的演算法按鈕（金色 = 已選取）
   - **Reveal algorithm**：開啟（預設）→ 演算法存入 metadata，解密時自動辨識；關閉 → 演算法隱藏，解密方需手動選擇
   - **Author / Password hint**：可設定作者名稱與密碼提示（解密時自動顯示）
   - **Mode / Iterations**：All-In-One（多層融合）或 Layered（每層獨立包裝）與迭代加密次數
4. 點選 **🔒 Encrypt & Save**，選擇輸出路徑

**解密檔案：**
1. 在右側「Decrypt」區塊點選 **Browse**（或拖拉 .isd）
2. **File Metadata** 區塊自動顯示：
   - 演算法（若已儲存，標示「✓ auto-detected」）
   - 密碼提示（加密時設定的 hint）
   - 作者名稱
3. 若演算法被隱藏，會出現手動演算法選擇 Bar（⚠ 警示）
4. 輸入密碼後點選 **🔓 Decrypt & Save**

### Tab 2 — 文字加密

1. 在輸入框輸入文字（或載入 `.isd` / `.txt`）
2. 輸入密碼、選擇演算法
3. 點選 **🔒 Encrypt**
4. 加密結果顯示在下方輸出框
5. 可選：**複製到剪貼簿** / **存成 .txt** / **存成 .isd**

解密：將加密文字貼入輸入框，輸入密碼後點 **🔓 Decrypt**。

### PGP 兩段式加密流程

選擇 **PGP / PGP-Multi / PGP-Escrow** 演算法時，工具執行兩段式加密：

```
原始資料 → [內層加密 (對稱)] → [PGP 信封 (公鑰包裝)]
             (e.g. AES-256-GCM + 密碼)    (RSA-4096 OAEP + AES-GCM)
```

**加密步驟：**
1. 在 Advanced Settings 選擇 PGP / PGP-Multi / PGP-Escrow
2. 在出現的 **PGP 面板**中：
   - 選擇**內層演算法**（AES-256-GCM 等）與對應密碼
   - 匯入一或多個**收件人公鑰**（`.pem`）
   - （PGP-Escrow）額外匯入 Escrow 公鑰
3. 點 **🔒 Encrypt & Save**

**解密步驟：**
1. 拖入 `.isd`，工具自動偵測 PGP 模式並顯示**私鑰匯入列**
2. 匯入自己的私鑰 `.pem`
3. 點 **🔓 Decrypt & Save**

**生成 RSA 金鑰對（程式碼）：**
```python
from core.engine import EncryptionEngine
priv_pem, pub_pem = EncryptionEngine.pgp_generate_keypair(bits=4096)
```

### Tab 3 — 混合加密

適合進階使用者，可建構多階段加密管線：

1. 點選 **＋ Add Stage** 新增加密階段
2. 每個階段獨立設定演算法與密碼
3. 選擇模式：
   - **Layered**：所有階段的加密層次融合在一起，整體打包為 **單一 `.isd`**；若拿到 File Tab 只解密一次，只能剝去最外層加密，得到的仍是加密的亂碼（非可識別的 `.isd`）
   - **Nested**：每個階段各自封裝為獨立 `.isd`；若拿到 File Tab 解密一次，可直接得到 **下一層完整的 `.isd` 檔**；重複操作即可逐層還原原始檔案
4. 選擇輸入為檔案或文字
5. 點選 **🔒 Encrypt** 執行

解密時需要以**相同的階段設定**（演算法 + 密碼）進行反向操作。

### Tab 4 — 大檔案模式

處理 GB 級大檔案：

**加密：**
1. 選擇來源檔案
2. 設定分段大小（預設 64 MB）
3. 建構加密管線（同 Tab 3）
4. 選擇輸出目錄
5. 點選 **🔒 Start Chunked Encryption**
6. 產出：多個 `chunk_XXXX.isd` + `manifest.json`

**解密（還原）：**
1. 切換到 Decrypt 操作
2. 選擇 `manifest.json`
3. 輸入密碼
4. 指定輸出檔名
5. 點選 **🔓 Reassemble & Decrypt**

---

## 專屬格式 `.isd`

所有加密輸出均使用此格式（副檔名 `.isd`），確保只有 CryptoTool Pro 能正確解讀：

```
CONTENT="""<Base64 編碼的加密資料>"""
NOTE="""<JSON 元資料>"""
```

NOTE 包含加密日期、作者、演算法、密碼提示等完整資訊，方便管理與辨識。

---

## 兩種加密模式

### Layered 模式（預設）
```
原始資料 → 加密₁ → 加密₂ → ... → 加密ₙ → 單一 .isd
```
**一個內容多階段加密，所有層次融合後封裝為單一 `.isd`。**

特性：
- 解密方需要提供**完整加密鏈**（所有演算法與密碼）才能一次還原
- 若只拿去 File Tab 解密一次，依舊得到加密亂碼——因為外層只是整體的一層，無法獨立解開內部
- 適合「必須一口氣完整解開」的情境

### Nested 模式
```
原始資料 → .isd₁ → .isd₂ → ... → .isdₙ
```
**一個內容多次單階段加密，每一次都是一個完整 `.isd` 的包裝。**

特性：
- 拿最外層 `.isd` 到 File Tab 解密一次，即可得到**完整的下一層 `.isd` 檔案**
- 重複以 File Tab 逐層解密，最終還原原始資料
- 適合「逐步解鎖、分段授權」的情境（例如需要不同人/金鑰逐層解開）

---

注意：`bytefile` 這個詞在專案中有兩個含義：

1. 作為「金鑰類型 (`bytefile`)」時，代表使用某個已存在檔案（現在通常是 `.isd`）的原始內容或其 hash 作為密鑰來源。
2. 作為檔案格式/副檔名，專案輸出檔案現在使用副檔名 `.isd`（歷史上曾使用 `.bytefile`，現已改名）。

程式內部的 `ByteFile` 類別仍維持處理此封裝格式的責任，輸出副檔會使用 `.isd`。

---

## 授權

本工具僅供個人學習與合法用途使用。
