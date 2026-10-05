# ⚡ Super File Converter

> 圖片、影片、PDF、表格的常用轉換都在一個視窗裡：可以一個一個設定轉，也可以設好規則後直接把檔案拖進來。

原本是兩支獨立程式（完整版 Super File Converter ＋ 拖放版 Quick Converter），現在合成一個視窗，拖放版是第一個分頁。

## 分頁

| 分頁 | 做什麼 |
|---|---|
| ⚡ 快速拖放 | 先加入轉換規則（可以多條，例如圖片同時轉 PNG 和 ICO），再把檔案或整個資料夾拖進來，結果產生在**原檔案旁邊**。拖進來的格式不符合任何規則時，會跳出對話框列出可用的轉換讓你勾選。同名檔案可以每次詢問、自動覆蓋或自動加後綴。 |
| 🖼 圖片 | 批次轉 PNG、JPEG、BMP、TIFF、WEBP、GIF、TGA、ICO（ICO 可勾選多種尺寸） |
| 🎬 影片 | 轉 MP4、AVI、MKV、MOV、WEBM、FLV、WMV、TS、GIF，或只取聲音（MP3 / WAV / FLAC / AAC） |
| ✂ 影片擷取 | 逐格匯出圖片（PNG / JPEG）與分離音訊，存到 `{影片名稱}/frames/`、`.../audio/` |
| 📄 圖片→PDF | 多張圖片調整順序後合成 PDF（JPEG 用 img2pdf 無損嵌入） |
| 📋 PDF 轉換 | PDF → 純文字 `.txt`、Word `.docx`（pdf2docx）、每頁一張投影片的 `.pptx` |
| 📊 表格轉換 | Excel → 每個工作表一個 CSV / Parquet（`報表.[Sales].csv`）；符合這個命名的 CSV / Parquet 會自動合併回同一個 `.xlsx`，右側有合併預覽 |

右上角可以切換深色 / 淺色主題。耗時的轉換都在背景執行，視窗不會卡住。

影片相關功能需要 **FFmpeg**（PATH 上，或裝在 `C:\ffmpeg\bin`）。

## 使用方式

以下在 PersonalToolZoo repo 根目錄執行：

```powershell
.\scripts\setup-venv.ps1 fast-file-converter
.\tools\fast-file-converter\.venv\Scripts\python.exe tools\fast-file-converter\GUI__FastFileConverter.py
.\scripts\build.ps1 fast-file-converter
```

## 專案結構

```
GUI__FastFileConverter.py   # 進入點
core/                       # 轉換引擎（不含畫面）
  quick.py                  #   快速拖放的規則表與轉換（原 GUI__QuickConverter.py 的邏輯）
  image_converter.py  video_converter.py  video_extractor.py  ffmpeg_utils.py
  pdf_maker.py  pdf_extractor.py  table_converter.py
gui/
  main_window.py            # 主視窗（TkinterDnD 視窗 + 分頁）
  tabs/                     # 每個分頁一個檔案；quick_tab.py 是快速拖放
tests/                      # 實際轉檔的測試
```

新增分頁：繼承 `gui/tabs/base_tab.BaseTab`，在 `gui/main_window.py` 的 `_TABS` 註冊。
新增輸出格式：改 `core/image_converter.py` 或 `core/video_converter.py` 的格式表（快速拖放的規則會自動跟著變）。

---

## 交接

| 項目 | 內容 |
|---|---|
| 入口 | `GUI__FastFileConverter.py` |
| 版本號 | `version.py` 的 `__version__` → exe 檔名 `SuperFileConverter(vX.Y.Z).exe`、視窗標題 `Super File Converter vX.Y.Z` |
| 環境 | 有第三方套件 → `tools\fast-file-converter\.venv` |
| 依賴 | Pillow、img2pdf、PyMuPDF、pdf2docx、python-pptx、pandas、openpyxl、pyarrow、sv-ttk、tkinterdnd2；上限依原專案實際在用的版本訂。**pandas 是 3.x**：這個工具是在 pandas 3 上開發測過的（跟 Excel Tool 相反） |
| 打包額外內容 | `collect_all`: `sv_ttk`（主題 .tcl）、`tkinterdnd2`（tkdnd DLL）；`hiddenimports` 沿用原本 spec 的清單 |
| 測試 | `.\tools\fast-file-converter\.venv\Scripts\python.exe -m unittest discover -s tools\fast-file-converter\tests -v`（5 個：圖片、影片（需要 ffmpeg）、表格、PDF 實際轉檔，以及主視窗有 7 個分頁） |
| Release tag | `SuperFileConverter_vX.Y.Z` |

### 注意事項

- 整併時修掉的問題：`run_ffmpeg` 先讀完 stdout 才讀 stderr，ffmpeg 警告一多就兩邊互等卡死（改成另開執行緒讀 stderr）；
  `excel_to_format` 開了 Excel 沒關，原始檔在程式結束前一直被鎖住；ffmpeg 只找 PATH（多看 `C:\ffmpeg\bin`）。
- 拖放要靠主視窗是 `TkinterDnD.Tk()`；沒裝 tkinterdnd2 時其他分頁照常，快速拖放分頁會顯示提示。
