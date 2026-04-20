# 🔐 CryptoTool Pro

一款功能強大的加密/解密桌面工具，支援多種加密演算法、專屬 `.bytefile` 格式、多階段混合加密，以及大檔案分段處理。

> **v1.2.0** 新增：AlgoBar 演算法選擇器、Advanced Settings 移入加密卡片、演算法可見性開關、解密側自動顯示 hint + 演算法

---

## 功能特色

| 功能 | 說明 |
|------|------|
| **檔案加密 (Tab 1)** | 加密任意檔案為 `.bytefile` 專屬格式，只有本工具能解開 |
| **文字加密 (Tab 2)** | 快速加密一段文字，支援 Base64 顯示、剪貼簿複製、存檔 |
| **混合加密 (Tab 3)** | 進階多階段加密管線，每階段可選不同演算法與密碼 |
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
| Base64 | 編碼 | 僅編碼，非加密（無需密碼） |

### 密碼類型

| 類型 | 說明 | 大小限制 |
|------|------|----------|
| **text** | 文字密碼 | ≤ 1024 字元 |
| **file** | 任意檔案的 SHA-256 雜湊 | ≤ 100 MB |
| **image** | 圖片檔的 SHA-256 雜湊 | ≤ 50 MB |
| **video** | 影片檔的 SHA-256 雜湊 | ≤ 200 MB |
| **bytefile** | `.bytefile` 內容的 SHA-256 雜湊 | ≤ 50 MB |
| **txtfile** | 純文字檔（整篇或段落）內容的 SHA-256 雜湊 | ≤ 50 MB |

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

### v1.2.0
- **AlgoBar（演算法選擇器）**：Tab 1 Advanced Settings 的演算法選擇改為分段式按鈕 Bar，金色高亮已選、hover 時有暖金光暈效果
- **Advanced Settings 移入加密卡片**：現在位於 Encrypt 方框內的可折疊面板，不再佔用頁面底部空間
- **演算法可見性開關**：新增 "Reveal algorithm in .bytefile metadata" 切換鈕（預設開啟）；關閉時演算法不寫入 NOTE，解密需手動選擇
- **解密卡片 — File Metadata 面板**：拖入 .bytefile 後自動解析並顯示演算法（附 auto-detected 標籤）、密碼提示、作者資訊
- **解密側 — 密碼提示自動顯示**：加密時設定的 hint 在解密側自動顯示，金色突出
- **解密側 — 演算法隱藏警示**：若演算法被隱藏，顯示琥珀色警示並展開手動演算法選擇 Bar

### v1.1.0
- **拖拉支援**：Tab 1–4 中所有檔案/目錄輸入欄均可拖放檔案；含中文、空格的 Unicode 路徑均支援
- **Text Tab 拖拉**：可將 `.bytefile` 或文字檔直接拖放到輸入文字框自動載入
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
   - **Reveal algorithm**：開啟（預設）→ 演算法存入 .bytefile 元資料，解密時自動辨識；關閉 → 演算法隱藏，解密方需手動選擇
   - **Author / Password hint**：可設定作者名稱與密碼提示（解密時自動顯示）
   - **Mode / Iterations**：Simple 或 Node 包法，迭代加密次數
4. 點選 **🔒 Encrypt & Save**，選擇輸出路徑

**解密檔案：**
1. 在右側「Decrypt」區塊點選 **Browse**（或拖拉 .bytefile）
2. **File Metadata** 區塊自動顯示：
   - 演算法（若已儲存，標示「✓ auto-detected」）
   - 密碼提示（加密時設定的 hint）
   - 作者名稱
3. 若演算法被隱藏，會出現手動演算法選擇 Bar（⚠ 警示）
4. 輸入密碼後點選 **🔓 Decrypt & Save**

### Tab 2 — 文字加密

1. 在輸入框輸入文字（或載入 `.bytefile` / `.txt`）
2. 輸入密碼、選擇演算法
3. 點選 **🔒 Encrypt**
4. 加密結果顯示在下方輸出框
5. 可選：**複製到剪貼簿** / **存成 .txt** / **存成 .bytefile**

解密：將加密文字貼入輸入框，輸入密碼後點 **🔓 Decrypt**。

### Tab 3 — 混合加密

適合進階使用者，可建構多階段加密管線：

1. 點選 **＋ Add Stage** 新增加密階段
2. 每個階段獨立設定演算法與密碼
3. 選擇模式：
   - **Simple**：連續加密 N 次，最後包成一個 `.bytefile`
   - **Node**：每一層都包成 `.bytefile`，層層包裝
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
6. 產出：多個 `chunk_XXXX.bytefile` + `manifest.json`

**解密（還原）：**
1. 切換到 Decrypt 操作
2. 選擇 `manifest.json`
3. 輸入密碼
4. 指定輸出檔名
5. 點選 **🔓 Reassemble & Decrypt**

---

## 專屬格式 `.bytefile`

所有加密輸出均使用此格式，確保只有 CryptoTool Pro 能正確解讀：

```
CONTENT="""<Base64 編碼的加密資料>"""
NOTE="""<JSON 元資料>"""
```

NOTE 包含加密日期、作者、演算法、密碼提示等完整資訊，方便管理與辨識。

---

## 兩種加密模式

### Simple 模式（預設）
```
原始資料 → 加密₁ → 加密₂ → ... → 加密ₙ → .bytefile
```
多次加密疊加後，整體打包為一個 `.bytefile`。

### Node 模式
```
原始資料 → .bytefile₁ → .bytefile₂ → ... → .bytefileₙ
```
每一次加密都完整包裝為 `.bytefile`，解密時一層一層剝開。

---

## 授權

本工具僅供個人學習與合法用途使用。
