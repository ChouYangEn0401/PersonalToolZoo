# Advanced Excel Tool

一個**分頁式 Excel 工具**，以 [`infinity_treeview`](https://pypi.org/project/infinity-treeview/)
的虛擬捲動表格為核心，採 **MVC + 操作註冊表** 架構（GUI 與未來 CLI 共用同一批純運算）。

分頁（Phase 1 為空殼，逐階段填入）：
🧹 整理單檔　🔍 比對雙檔（Single/Neighbor/Two-Side 差異）　📂 合併　🔎 AB 比對　🔧 條件清理　📊 集合運算

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

