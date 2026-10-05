# File Renamer

> 把檔案拖進視窗，用正規表達式或雜湊批次改名；改之前先看預覽，改錯了可以復原。

## 功能

- **正規表達式**：`尋找` / `取代成`，取代可以用 `\1`、`\2` 引用括號內容，可選不分大小寫。
  例：尋找 `^IMG_(\d+)`、取代成 `照片_\1` → `IMG_0012.jpg` 變 `照片_0012.jpg`。
- **雜湊改名**（保留副檔名）：
  - 檔名雜湊（SHA-256）：跟舊版的「Rename With Hash」一樣，用原檔名算雜湊，拿來匿名化檔名。
  - 檔案內容雜湊（SHA-256）：內容相同的檔案會得到相同的名字，適合整理、去重複。
- **即時預覽**：規則一改，表格就更新「原檔名 → 新檔名」。下列情況會標紅而且不會套用：
  規則寫錯、新檔名不合法、同一批裡新檔名重複、目標檔名已經存在。
- **↩ 復原上次改名**：把剛剛那一批改回原名。

## 使用方式

以下在 PersonalToolZoo repo 根目錄執行：

```powershell
.\scripts\setup-venv.ps1 file-renamer
.\tools\file-renamer\.venv\Scripts\python.exe tools\file-renamer\main.py
.\scripts\build.ps1 file-renamer
```

---

## 交接

| 項目 | 內容 |
|---|---|
| 入口 | `main.py` |
| 版本號 | `version.py` 的 `__version__` → exe 檔名 `FileRenamer(vX.Y.Z).exe`、視窗標題 `File Renamer vX.Y.Z` |
| 環境 | 有第三方套件 → `tools\file-renamer\.venv` |
| 依賴 | `tkinterdnd2<1`（拖放） |
| 打包額外內容 | `icon` 與 `include`: `data/FileRenamer.ico`；`collect_all`: `tkinterdnd2`（tkdnd 的 DLL） |
| 測試 | `.\tools\file-renamer\.venv\Scripts\python.exe -m unittest discover -s tools\file-renamer\tests -v`（5 個，含實際改名再復原） |
| Release tag | `FileRenamer_vX.Y.Z` |

### 注意事項

- 舊版（`Python Projects\。File Renamer`）會多開一個空白視窗：它的 `FileRenamerApp` 忽略傳進來的 root、
  自己又建了一個 `TkinterDnD.Tk()`。現在只有一個視窗。
- 舊版的「左右兩個清單＋不匹配清單」換成一張預覽表；不想改的檔案用「移除選取」拿掉即可。
