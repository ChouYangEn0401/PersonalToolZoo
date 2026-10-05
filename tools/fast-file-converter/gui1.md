# GUI1 — Super File Converter（完整功能版）

一個以桌面 GUI 為主的快速檔案轉換工具（以 Python / Tkinter + sv-ttk 實作），整合圖片、影片、PDF 以及表格資料（Excel / CSV / Parquet）的常見轉換與擷取功能，設計為簡單好用且易於擴充。支援深色／淺色主題一鍵切換。

---

## 主要特色

- **圖片轉換**：批次無損化轉換（PNG、JPEG、BMP、TIFF、WEBP、GIF、TGA、ICO 等），支援 ICO 多尺寸輸出。
- **影片轉檔**：支援 MP4、AVI、MKV、MOV、WEBM、FLV、WMV、TS、GIF 等，並能直接輸出音訊（MP3 / WAV / FLAC / AAC）。
- **影片擷取**：逐幀導出（PNG / JPEG）與音訊分離，輸出自動整理為 `{影片名稱}/frames/` 與 `.../audio/` 子資料夾。
- **圖片 → PDF**：可調整頁序並輸出高品質 PDF（優先使用 img2pdf 無損嵌入）。
- **PDF 轉換**：抽取為純文字 `.txt`、Word `.docx`（pdf2docx）或每頁轉投影片圖片 `.pptx`。
- **表格轉換**：Excel ↔ CSV / Parquet 雙向轉換（詳見下方說明）。
- **現代 UI**：sv-ttk Windows 11 風格主題，深色 / 淺色模式一鍵切換，所有耗時操作以背景執行緒執行，介面不卡頓。

---

## 執行方式

```bash
python GUI__FastFileConverter.py
```

---

## 表格轉換說明（Excel ↔ CSV / Parquet）

### Excel → CSV 或 Parquet

每個工作表獨立輸出為一個檔案，命名規則如下：

```
{檔名}.xlsx  →  {檔名}.[{工作表名稱}].csv
{檔名}.xlsx  →  {檔名}.[{工作表名稱}].parquet
```

範例：`報表.xlsx`（含 Sales、Marketing 兩個工作表）→ `報表.[Sales].csv` + `報表.[Marketing].csv`

### CSV / Parquet → Excel

符合 `{檔名}.[{工作表名稱}].{csv|parquet}` 命名規則的檔案，會自動辨識並合併回同一個 `.xlsx`，每個檔案對應一個工作表。不符合規則的檔案則各自產生一個單頁 Excel。

介面右側提供**合併預覽**，添加檔案後即時顯示最終 Excel 的工作表結構。

---

## 各分頁使用說明

**🖼 圖片轉換** — 添加圖片（支援多選），選擇輸出格式與輸出資料夾後點擊「開始轉換」。選 `ICO` 時可勾選欲輸出的尺寸。

**🎬 影片轉換** — 選取影片，選擇輸出格式（含音訊格式）。程式自動偵測 FFmpeg。

**✂ 影片擷取** — 支援「影格 + 音訊」、「僅影格」、「僅音訊」三種模式。

**📄 圖片 → PDF** — 添加多張圖片後可透過上下移動調整頁序，再輸出 PDF。

**📋 PDF 轉換** — 選擇 PDF 與輸出目錄，選擇輸出格式（txt / docx / pptx）。

**📊 表格轉換** — 見上方「表格轉換說明」章節。

---

## 開發者提示

- 新增輸出格式：修改 `core/video_converter.py` 或 `core/image_converter.py` 中的格式設定字典。
- 新增分頁：繼承 `gui/tabs/base_tab.BaseTab`，並在 `gui/main_window.py` 的 `_TABS` 清單中註冊。
