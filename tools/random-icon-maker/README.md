# Random Icon Maker

> 輸入一個種子，用 9 種演算法產生隨機圖示（漸層、條紋、棋盤格、雜訊…），預覽後存成 ICO 或 PNG——
> 給新做的小工具當圖示用。

## 功能

- 種子可以自己輸入（-1000000 ～ 1000000）或按「🎲 隨機」；**同一個種子永遠產生同一組圖**，
  喜歡的圖示記下種子，之後可以用別的尺寸重新產生。
- 尺寸：32 / 64 / 128 / 256。
- 9 張一起預覽，勾選要的存起來；ICO 會內含 16～256 的多種尺寸（不超過選的尺寸），也可以存 PNG。
- 檔名沿用舊版格式：`[2026-10-05 21-30-00] algo3(596481).ico`，預設存到「圖片\Random Icons」。

## 使用方式

以下在 PersonalToolZoo repo 根目錄執行：

```powershell
.\scripts\setup-venv.ps1 random-icon-maker
.\tools\random-icon-maker\.venv\Scripts\python.exe tools\random-icon-maker\main.py
.\scripts\build.ps1 random-icon-maker
```

---

## 交接

| 項目 | 內容 |
|---|---|
| 入口 | `main.py`（GUI）；演算法在 `icon_algorithms.py` |
| 版本號 | `version.py` 的 `__version__` → exe 檔名 `RandomIconMaker(vX.Y.Z).exe`、視窗標題 `Random Icon Maker vX.Y.Z` |
| 環境 | 有第三方套件 → `tools\random-icon-maker\.venv` |
| 依賴 | `pillow<13`（舊版鎖 11.0.0；12.x 的輸出經測試逐像素相同） |
| 打包額外內容 | 無 |
| 測試 | `.\tools\random-icon-maker\.venv\Scripts\python.exe -m unittest discover -s tools\random-icon-maker\tests -v`（對照舊版輸出） |
| Release tag | `RandomIconMaker_vX.Y.Z` |

### 注意事項

- 舊版（`Python Projects\64x64 Random Icon Maker\GeneratedImageExporter.py`）是命令列程式：
  輸入不是數字時會因為 `seeds` 變成字串而崩潰，圖示也直接存在「目前所在的資料夾」。舊 readme 寫 5 種演算法，實際是 9 種。
- **不要改 `ALGORITHMS` 的順序或演算法內的亂數呼叫順序**：9 個演算法共用同一串亂數，順序一變，
  同一個種子產生的圖就跟以前不一樣了。測試會抓到。
