# Advanced Excel Tool

一個**分頁式 Excel 工具**，以 [`infinity_treeview`](https://github.com/ChouYangEn0401/Python-Infinity-Treeview)
的虛擬捲動表格為核心，採 **MVC + 操作註冊表** 架構（GUI 與未來 CLI 共用同一批純運算）。

三個工作台（依「進出表格數」分，各自獨立、無隱藏全域狀態）：

| 分頁 | 業務 | 內容 |
|---|---|---|
| 🧹 核心整理 | 1 表 → 1 表 | 連續疊加操作、可 undo/還原：刪/留/重命名/重排欄、去重、刪空列欄、per-欄 NaN、篩選、多欄排序、條件清理、保留分組極值、比對/查重複值、合併濃縮、透視表、依另一檔合併/刪列。右鍵看教學。 |
| 🔗 合併 | N 表 → 1 表 | 多檔載入標記 主表/納入/略過 → 直接疊加 / 共同欄疊加 / 交集 / 聯集 / 差集。 |
| 🔍 比較 | 2 表 → 檢視 | diff 三模式（Single / Neighbor / Two-Side，還原高級樣式、點表頭彈選單套清洗）＋ AB 人工審核。 |

> **連續疊加(ETL)**：核心整理台就是一個工作 session — 載入一張表後可一直套操作、隨時 undo/還原。
> **開放給別人用**：`excel_tool.core`（operations + registry）與 `cli` 是可重用 API，GUI 只是消費者。

## 執行

以下都在 PersonalToolZoo repo 根目錄執行。依賴寫在 `tools/excel-tool/requirements.txt`：
`infinity-treeview` 沒有發布到 PyPI，直接從 GitHub 的 `release_0.2.0` tag 安裝；
pandas 釘在 2.x（原因見該檔註解）。

```powershell
.\scripts\setup-venv.ps1 excel-tool          # 建立隔離環境（只要一次，需要 git 與網路）

cd tools\excel-tool
.\.venv\Scripts\python.exe GUI_AdvancedExcelTool.py   # GUI
.\.venv\Scripts\python.exe -m excel_tool.cli list     # 列出可用操作（CLI 與 GUI 共用核心）
.\.venv\Scripts\python.exe -m excel_tool.cli apply drop_columns --in a.xlsx --out b.xlsx --param columns=foo,bar
cd ..\..

.\scripts\build.ps1 excel-tool         # 打包成 exe（含冒煙測試）→ dist\excel-tool\
```

## 架構（MVC，btn → callback → 純運算）

```
excel_tool/
├── core/            ← 無 GUI：TableSession(Model)、operations(純函式)、
│   │                  registry(參數規格,GUI/CLI 共用)、diff、transforms
│   └── ...
├── gui/             ← View+Controller：app(Notebook 殼)、colored_table、各分頁
└── cli.py           ← 以同一 registry 從命令列驅動
GUI_AdvancedExcelTool.py  ← GUI 進入點
```

---

## 交接

| 項目 | 內容 |
|---|---|
| 入口 | `GUI_AdvancedExcelTool.py`（GUI）；`python -m excel_tool.cli`（CLI，共用同一個操作註冊表） |
| 版本號 | `excel_tool/__init__.py` 的 `__version__` → exe 檔名 `GUI_AdvancedExcelTool(vX.Y.Z).exe`、視窗標題 `Advanced Excel Tool vX.Y.Z` |
| 環境 | 專屬 `tools\excel-tool\.venv`（build 時自動建立／同步；第一次需要 git 與網路） |
| 依賴 | `infinity-treeview`（作者自己的套件，沒上 PyPI，從 GitHub tag `release_0.2.0` 安裝）、`pandas>=2.0,<3`、`openpyxl`、`tkinterdnd2` |
| 打包額外內容 | `collect_all: infinity_treeview`（把它的資料檔一起打包） |
| 測試 | repo 裡沒有自動化測試。改了 `excel_tool/core` 的話，至少用 CLI 把動到的操作跑一次 |
| Release tag | `ExcelTool_vX.Y.Z` |

常用指令（repo 根目錄）：

```powershell
.\scripts\build.ps1 excel               # build + 冒煙測試
.\scripts\release.ps1 excel patch       # 發新版
```

### 注意事項

- **pandas 不能直接升 3.x**：`core/operations.py` 的 `aggregate_with_separator`（合併濃縮）
  用 `x.astype(str)` 再 join，pandas 3 的 `astype(str)` 會保留 NaN，遇到空格就 `TypeError`。
  要升級得先改這段（先處理空值再轉字串，並決定空值要顯示成什麼——pandas 2 下目前是 `nan`），
  再把所有操作跑過一輪。
- 新增操作的方式：在 `core/operations.py` 寫純函式並 `register(Operation(...))`，
  GUI 的選單和 CLI 會自動出現，不用改 GUI 程式碼。
