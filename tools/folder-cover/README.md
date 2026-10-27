# Folder Cover

> 把資料夾在檔案總管裡的圖示換成裡面的一張圖：相簿、漫畫、影集、專案資料夾一眼就認得。

## 功能

- 把資料夾拖進視窗（或按「＋ 加入資料夾」），可以一次加很多個。
- 右邊列出資料夾裡的圖片（檔名是 `cover`、`folder`、`poster`、`front` 的排前面），也可以「選其他圖片…」或直接把圖片拖進來。
- 預覽封面，選「裁成正方形（取中間）」或「整張保留（旁邊補透明）」。
- **設成這個資料夾的封面**／**移除封面（恢復預設圖示）**；左邊清單顯示每個資料夾目前是預設還是自訂圖示。
- **每個資料夾自動套用**：一次幫一整批資料夾換封面，用你選好的圖；沒選的用 cover／folder 開頭的圖或第一張圖，沒有圖片的會略過並標示。

## 怎麼做到的

跟檔案總管「內容 → 自訂 → 變更圖示」一樣：

1. 把圖片裁成正方形，存成內含 16～256 多種尺寸的 `folder-cover.ico`，放進那個資料夾（隱藏）。
2. 呼叫 Windows 的 `SHGetSetFolderCustomSettings`：它寫 `desktop.ini`（`IconResource=folder-cover.ico,0`）、
   把資料夾設成唯讀讓檔案總管去讀 `desktop.ini`，並通知檔案總管重新整理。
3. 圖示用**相對路徑**，資料夾搬家、換磁碟機都不會失效。

移除時只拿掉圖示那幾行；`desktop.ini` 還有其他設定（例如資料夾的提示文字）就保留，沒有了才刪掉並恢復資料夾屬性。

## 使用方式

以下在 PersonalToolZoo repo 根目錄執行：

```powershell
.\tools\folder-cover\run.bat                 # 從原始碼執行（自動用 tools\folder-cover\.venv，沒有就建好）
.\scripts\build.ps1 folder-cover             # 打包成 exe
```

---

## 交接

| 項目 | 內容 |
|---|---|
| 入口 | `main.py`（畫面）；做事的在 `cover.py`（圖片轉 ico、套用、移除、目前的圖示），可以單獨測試 |
| 版本號 | `version.py` 的 `__version__` → exe 檔名 `FolderCover(vX.Y.Z).exe`、視窗標題 `Folder Cover vX.Y.Z` |
| 環境 | 有第三方套件 → `tools\folder-cover\.venv` |
| 依賴 | `pillow<13`（裁切、轉 ico）、`tkinterdnd2<1`（拖放）；只支援 Windows（`shell32`、`shlwapi`、`kernel32` 的 API） |
| 資料 | 不存任何設定；寫入的只有使用者選的資料夾裡的 `folder-cover.ico` 與 `desktop.ini` |
| 打包額外內容 | `collect_all`: `tkinterdnd2`（tkdnd 的 DLL） |
| 測試 | `.\tools\folder-cover\.venv\Scripts\python.exe -m unittest discover -s tools\folder-cover\tests -v`（7 個：ico 尺寸與裁切、在暫存資料夾實際套用／移除、保留其他 desktop.ini 設定、畫面走一遍） |
| Release tag | `FolderCover_vX.Y.Z` |

### 注意事項

- 前身是 `Python Projects\Change Folder Cover (failes)`（作者標了 failed）。舊版失敗的原因：
  沒有先裁成正方形就存 ICO、`desktop.ini` 用正斜線的絕對路徑寫圖示、沒有通知檔案總管更新快取（看起來就像沒作用）、`desktop.ini` 沒隱藏。
  原始碼留在 `chore(folder-cover): import …` 那個 commit。
- 檔案總管偶爾會沿用舊的圖示快取：按 F5，或關掉再開那個資料夾的上一層即可。
- 網路磁碟、唯讀媒體、沒有權限的資料夾會失敗，清單的狀態欄會寫原因。
