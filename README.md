# Advanced Excel Tool

一個**分頁式 Excel 工具**，以 [`infinity_treeview`](https://pypi.org/project/infinity-treeview/)
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

```bash
pip install path/to/PythonInfinityTreeview/dist/infinity_treeview-0.2.0-py3-none-any.whl
python GUI_AdvancedExcelTool.py           # GUI
python -m excel_tool.cli list             # 列出可用操作（CLI 與 GUI 共用核心）
python -m excel_tool.cli apply drop_columns --in a.xlsx --out b.xlsx --param columns=foo,bar
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

# 使用說明書教學
## 版本限定
```commandline
python 3.11 以上
```

## 環境預備
請在專案 root folder 下，建立 `.env` 文件
```text
```
請在專案 root folder 下，建立 以下資料夾 [``, ``, ``]

## 使用方式
### 簡單訪問服務流程 \[初階]
```text
```

### 參數化訪問方式 \[中階]
```text
```

## 其他補充說明
...

