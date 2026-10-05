# Super File Converter

本專案包含兩個獨立的 GUI 工具，共用同一套 `core/` 轉換引擎：

| 工具 | 入口檔案 | 說明文件 | 定位 |
|---|---|---|---|
| **Super File Converter** | `GUI__FastFileConverter.py` | [gui1.md](gui1.md) | 完整功能 GUI，分頁式操作 |
| **Quick Converter** | `GUI__QuickConverter.py` | [gui2.md](gui2.md) | 拖放即轉換的快速模式 |

---

## 先決條件

- **Python 3.10+**
- **FFmpeg**（影片相關功能需安裝並加入 PATH）

## 快速安裝與執行

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1   # Windows PowerShell

pip install -r requirements.txt
```

執行完整 GUI：
```bash
python GUI__FastFileConverter.py
```

執行快速轉換器：
```bash
python GUI__QuickConverter.py
```

---

## 專案結構

```
GUI__FastFileConverter.py   # GUI1 啟動入口（完整功能）
GUI__QuickConverter.py      # GUI2 啟動入口（快速拖放轉換）
requirements.txt
gui/                        # GUI1 的介面模組
  main_window.py
  tabs/
    base_tab.py
    image_tab.py
    video_tab.py
    extractor_tab.py
    pdf_maker_tab.py
    pdf_extract_tab.py
    table_tab.py
core/                       # 共用轉換引擎
  image_converter.py
  video_converter.py
  ffmpeg_utils.py
  video_extractor.py
  pdf_maker.py
  pdf_extractor.py
  table_converter.py
```

---

## 套件依賴

| 套件 | 用途 |
|---|---|
| `Pillow` | 圖片格式轉換 |
| `img2pdf` | 圖片無損嵌入 PDF |
| `PyMuPDF` | PDF 文字抽取、頁面渲染 |
| `pdf2docx` | PDF → Word 轉換 |
| `python-pptx` | PDF → PPTX 輸出 |
| `pandas` | 表格資料讀寫核心 |
| `openpyxl` | Excel 讀寫引擎 |
| `pyarrow` | Parquet 讀寫引擎 |
| `sv-ttk` | Windows 11 風格 UI 主題 |
| `tkinterdnd2` | 拖放功能（GUI2 使用） |

---

## 授權

請自行補上授權資訊（如 MIT License）。
