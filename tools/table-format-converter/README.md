# Table Tool

一個輕量的桌面小工具，讓你把 **Tab 分隔表格**（直接從 Excel 複製貼上）或 **Markdown 表格**丟進去，立刻預覽，然後一鍵輸出成你要的格式。

---

## 功能

| 功能 | 說明 |
|------|------|
| 自動偵測輸入格式 | Tab 分隔（Excel 複製貼上）或 Markdown `\| col \|` 格式，自動判斷，不用手動選 |
| 表格預覽 | 解析後立即在視窗內顯示為可捲動表格，交錯行底色方便閱讀 |
| 複製 MD 格式 | 輸出對齊好的 Markdown 表格到剪貼簿，可直接貼進 `.md` 檔 |
| 複製 Tab 格式 | 輸出 Tab 分隔內容到剪貼簿，可直接貼回 Excel |
| 存成 `.csv` | 支援 `utf-8-sig` / `utf-8` / `cp950` 編碼，解決 Excel 中文亂碼問題 |
| 存成 `.xlsx` | 直接產生 Excel 檔，自動調整欄寬 |

---

## 環境需求

- Python **3.11** 以上
- tkinter（Python 內建，通常不需另外安裝）
- openpyxl（僅在使用「存成 .xlsx」時需要）

---

## 安裝

```bash
# 複製專案
git clone https://github.com/ChouYangEn0401/PersonalToolZoo.git
cd PersonalToolZoo

# （選用）安裝 xlsx 支援
pip install openpyxl
```

> `requirements.txt` 目前列的是 PyInstaller 打包用的依賴，日常執行只需要上面的套件。

---

## 使用方式

```bash
python main.py
```

1. 把表格文字貼進上方輸入框（Tab 分隔或 Markdown 格式皆可）
2. 按 **▶ 解析 / 預覽**，下方會出現渲染後的表格
3. 依需求點擊輸出按鈕：
   - **📋 MD → 剪貼簿**：複製 Markdown 格式
   - **📋 Tab → 剪貼簿**：複製 Tab 格式（可貼回 Excel）
   - **💾 存成 .csv**：選擇路徑與編碼後儲存
   - **💾 存成 .xlsx**：選擇路徑後儲存 Excel 檔

---

## 支援的輸入格式

### Tab 分隔（從 Excel 複製貼上）
```
姓名	部門	分機
Alice	工程	1001
Bob	設計	1002
```

### Markdown 表格
```
| 姓名  | 部門 | 分機 |
|-------|------|------|
| Alice | 工程 | 1001 |
| Bob   | 設計 | 1002 |
```

---

## 專案結構

```
PersonalToolZoo/
├── main.py          # 主程式（GUI + 全部邏輯）
├── requirements.txt # PyInstaller 打包依賴
├── src/             # 預留的模組目錄（尚未使用）
├── data/            # 資料目錄
└── docs/            # 文件目錄
```

