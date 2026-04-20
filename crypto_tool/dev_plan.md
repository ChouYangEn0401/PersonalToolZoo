# CryptoTool Pro — 開發計畫

## 專案概述
一款專業的加密/解密 GUI 工具，基於 Python + tkinter (ttkbootstrap)，支援多種加密演算法，
具備專屬 `.isd` 格式（輸出副檔名），確保只有本程式能解開加密內容。

---

## 架構設計

```
crypto_tool/
├── main.py                  # 程式進入點
├── requirements.txt         # 相依套件
├── core/
│   ├── __init__.py
│   ├── engine.py            # 加密引擎（所有演算法）
│   ├── bytefile.py          # 專屬格式處理（輸出副檔名 .isd；處理封裝格式）
│   └── utils.py             # 工具函式
├── gui/
│   ├── __init__.py
│   ├── app.py               # 主視窗 / Notebook
│   ├── theme.py             # 主題 & 色彩配置
│   ├── widgets.py           # 共用自訂元件
│   ├── tab_file.py          # Tab 1：檔案加密/解密
│   ├── tab_text.py          # Tab 2：文字加密/解密
│   ├── tab_mixture.py       # Tab 3：混合加密模式
│   └── tab_largefile.py     # Tab 4：大檔案模式
```

---

## 功能規格

### Tab 1 — 檔案模式
| 區塊 | 說明 |
|------|------|
| 左半 — 加密 | 選擇任意檔案 → 輸入密碼 → 產出 `.isd` |
| 右半 — 解密 | 選擇 `.isd` → 輸入密碼 → 還原原始檔案 |
| 進階設定（預設隱藏） | 演算法選擇、作者、密碼提示、加密模式、迭代次數 |

### Tab 2 — 文字模式
-- 文字輸入框支援：手動輸入、貼上、載入 `.isd`
- 加密後可選 base64 收尾（預設開啟）
- 輸出方式：
  1. 複製到剪貼簿
  2. 顯示在下方 Textbox
  3. 存成 `.txt` 或 `.isd`

### Tab 3 — 混合加密模式（進階玩家）
- 可新增多個加密階段，每階段獨立設定演算法 + 密碼
-- **Simple 模式**：資料連續加密 N 次 → 最後包成一個 `.isd`
-- **Node 模式**：每次加密都包成 `.isd`，層層包裝
- 支援檔案 & 文字輸入

### Tab 4 — 大檔案模式
- 設定分段大小（chunk size）
-- 分段讀取 → 分段加密 → 輸出多個 `.isd` + manifest.json
- 解密時讀取 manifest → 逐段解密 → 組裝還原

---

## 專屬格式 `.isd`

```
CONTENT="""<base64 編碼之加密資料>"""
NOTE="""<JSON 元資料>"""
```

### NOTE 欄位
```json
{
  "encryption_date": "2026-04-17T12:00:00",
  "author": "@anonymous",
  "password_hint": null,
  "algorithm": "AES-256-CBC",
  "key_type": "text",
  "mode": "simple",
  "iterations": 1,
  "mixture_chain": null,
  "original_filename": "document.pdf",
  "original_size": 12345,
  "chunk_info": null
}
```

---

## 支援的加密演算法

| 演算法 | 類型 | 金鑰長度 | 說明 |
|--------|------|----------|------|
| AES-256-CBC | 對稱區塊 | 256-bit | 預設，最常用 |
| AES-256-GCM | 認證加密 | 256-bit | 帶完整性驗證 |
| ChaCha20-Poly1305 | 認證串流 | 256-bit | 現代高效 |
| Blowfish-CBC | 對稱區塊 | 256-bit | 經典加密 |
| 3DES-CBC | 對稱區塊 | 192-bit | 向下相容 |
| XOR | 串流 | 256-bit | 輕量快速 |
| Base64 | 編碼 | 無 | 僅編碼，非加密 |

---

## 密碼類型

| 類型 | 說明 | 大小限制 |
|------|------|----------|
| text | 文字密碼 | 最長 1024 字元 |
| file | 任意檔案 hash 作為金鑰 | ≤ 100 MB |
| image | 圖片檔 hash 作為金鑰 | ≤ 50 MB |
| video | 影片檔 hash 作為金鑰 | ≤ 200 MB |
| bytefile | `.isd` 內容 hash 作為金鑰（key-type: 使用已輸出檔案內容或其 hash 作為金鑰來源） | ≤ 50 MB |

金鑰推導：PBKDF2-SHA256，100,000 次迭代，16-byte 隨機 salt。

---

## 兩種加密大模式

### 1. Simple（簡單暴力）— 預設
```
原始資料 → encrypt₁ → encrypt₂ → ... → encryptₙ → 包成 .isd
```
所有加密連續套用，最後整體包一次專屬格式。NOTE 記錄 mixture_chain。

### 2. Node（多次保護節點）
```
原始資料 → .isd₁ → .isd₂ → ... → .isdₙ
```
每一層都是完整的 `.isd`，解密時一層一層剝開。

---

註記：專案內的 `bytefile` 一詞有兩種用途：

1. 在 `core`/金鑰類型中，`bytefile` 作為 key-type，表示使用某個檔案（通常為 `.isd`）的內容或其 hash 作為金鑰來源。
2. 作為檔案格式時，輸出副檔名現為 `.isd`（歷史上曾為 `.bytefile`）。

---

## 技術選型

| 項目 | 選擇 |
|------|------|
| GUI | ttkbootstrap（darkly 主題） |
| 加密 | PyCryptodome |
| 金鑰推導 | PBKDF2-HMAC-SHA256 |
| 格式 | 自訂 `.isd` |
| 執行緒 | threading（防止 GUI 凍結） |

---

## 開發順序

1. ✅ 撰寫開發計畫 (dev_plan.md)
2. ✅ 實作 core/engine.py — 所有加密演算法
3. ✅ 實作 core/bytefile.py — 專屬格式
4. ✅ 實作 core/utils.py — 工具函式
5. ✅ 實作 gui/ — 四個分頁 + 主視窗
6. ✅ 實作 main.py — 進入點
7. ✅ 撰寫 README.md

## 後續改善 (v1.1.0)

8. ✅ 拖拉支援 — 所有檔案輸入欄位均支援 drag-and-drop (tkinterdnd2)
9. ✅ Unicode/編碼路徑安全 — 文字載入加入 UTF-8 → latin-1 fallback，DnD 路徑自動清理 `{}` 包裝
10. ✅ 暖金色主題 — 改為暖金/琥珀色配色，Labelframe 標題金色，加密按鈕改為 warning (amber)
11. ✅ Tooltip 說明 — 所有關鍵元件加入懸浮提示（演算法、密碼輸入、迭代次數、拖拉提示等）
