# ⬇️ Video Downloader

> 貼上網址就下載：yt-dlp 支援的約 1800 個網站（YouTube、Bilibili、X、IG、TikTok、Facebook…），
> 或直接貼 `.m3u8` / `.mpd` 串流網址。本機網頁 GUI，也可以當 CLI 用。

前身是只能處理單層 m3u8 的「M3U8 Downloader Pro」（舊程式在 git 歷史裡：`chore(video-downloader): import …`），
現在改用 [yt-dlp](https://github.com/yt-dlp/yt-dlp) 當引擎。

## 使用方式

以下在 PersonalToolZoo repo 根目錄執行：

```powershell
.\scripts\setup-venv.ps1 video-downloader
$py = ".\tools\video-downloader\.venv\Scripts\python.exe"

& $py tools\video-downloader\VideoDownloader.py                     # GUI：自動開瀏覽器 http://127.0.0.1:8765
& $py tools\video-downloader\VideoDownloader.py <網址> -p 1080p      # CLI
.\scripts\build.ps1 video-downloader                                # 打包成 exe（雙擊開 GUI，帶參數就是 CLI）
```

需要 **ffmpeg**（合併影像與聲音、轉 MP3）與 **Node / Bun / Deno 其中一個**（YouTube 需要）。標題列會顯示有沒有找到。

### GUI

- **加網址**：貼上（一次可以很多個）、按「📋 貼上」讀剪貼簿、或把連結直接拖進輸入框。
- **🔍 解析**：先看標題、長度、最高畫質、有哪些字幕；播放清單會列出每一支，勾選要下載的（存到以清單命名的子資料夾）。
- **⬇ 直接下載**：不解析，用選好的畫質直接開始。
- **畫質**：最相容 MP4（H.264，哪裡都能播）、最高畫質（VP9/AV1 → MKV）、4K / 1080p / 720p / 480p、只要聲音（MP3 / M4A）、自訂 format 字串。
- **下載中**：進度、速度、剩餘時間、目前步驟（下載影像 / 聲音、第幾段、合併、轉檔、嵌入字幕）；可以取消，
  取消或失敗後按「重試」會從已下載的部分接著下載。
- **紀錄**：下載過的檔案，「開啟位置」會在檔案總管選取該檔案，「再下載一次」用同樣的設定。
- **書籤小工具**：在 ⚙ 設定裡把「⬇ 送到下載器」拖到瀏覽器書籤列。之後在任何影片頁按一下，
  就會開啟這裡並自動解析該頁網址（只解析，按下載才會開始）。

### 進階：直接下載串流（舊版的使用情境）

網頁播放器背後常是 `.m3u8`（HLS）或 `.mpd`（DASH）：瀏覽器按 F12 → Network → 篩選 `m3u8`，把網址貼進來即可。
yt-dlp 會自動處理多畫質主清單（舊版會把子清單誤當成分段）、AES-128 加密分段、分段並行下載與續傳。
如果伺服器回 403，在「進階」填上 `Referer: <影片所在頁面網址>`（需要的話再加 `User-Agent`），這取代了舊版的「網址前綴 / 後綴修正」。

需要登入才看得到的影片（會員、年齡限制）：設定裡選「用哪個瀏覽器的登入狀態」，Windows 上 Firefox 最穩
（Chrome / Edge 新版的 cookie 加密常讓 yt-dlp 讀不到）。**有 DRM 版權保護的串流（Netflix、Disney+ 等）無法下載**，這是刻意的。

### CLI

```powershell
VideoDownloader https://youtu.be/xxxx                         # 用設定裡的預設畫質
VideoDownloader https://youtu.be/xxxx -p audio-mp3 -o D:\Music
VideoDownloader https://youtube.com/playlist?list=xxxx --playlist -p 720p
VideoDownloader https://cdn.example.com/master.m3u8 --name 回放 -H "Referer: https://example.com/live"
VideoDownloader --help
```

## 設定

存在 `%APPDATA%\PersonalToolZoo\video-downloader\settings.json`，GUI 的 ⚙ 設定可以改：
下載位置（預設「下載\Video Downloader」）、檔名範本（yt-dlp 語法，例如 `%(uploader)s/%(title)s.%(ext)s`）、
預設畫質、同時下載幾支、每支同時抓幾段、限速、Proxy、字幕（語言、自動字幕、嵌入）、寫入影片資訊、嵌入縮圖、ffmpeg 位置。
下載紀錄在同一個資料夾的 `history.json`（最多 500 筆）。

---

## 交接

| 項目 | 內容 |
|---|---|
| 入口 | `VideoDownloader.py`（無參數 → `video_downloader/web/server.py` 的 GUI；有參數 → `video_downloader/cli.py`） |
| 版本號 | `version.py` 的 `__version__` → exe 檔名 `VideoDownloader(vX.Y.Z).exe`、GUI 標題 |
| 環境 | 有第三方套件 → `tools\video-downloader\.venv` |
| 依賴 | `yt-dlp[default]<2028`（網站常改版要常更新，上限刻意給寬）、`fastapi<1`、`uvicorn<1` |
| 共用程式 | `libs/toolzoo`：`ytdlp`（JS 執行環境、ffmpeg 位置）、`webapp`（啟動器）、`appdirs` |
| 打包額外內容 | `include`: `video_downloader/web/static`；`collect_all`: `yt_dlp_ejs`；uvicorn 的 hiddenimports |
| 測試 | `.\tools\video-downloader\.venv\Scripts\python.exe -m unittest discover -s tools\video-downloader\tests -v`（離線；web API 的 2 個測試需要先 `pip install httpx2`，沒裝會略過） |
| Release tag | `VideoDownloader_vX.Y.Z` |

### 注意事項

- 參數的組法：`options.py` 先組成 yt-dlp 命令列參數，再用 `yt_dlp.parse_options()` 轉成 API 選項——
  要加新選項時照 yt-dlp 的命令列文件加參數就好，不要手寫 postprocessor 的 dict。
- YouTube 抓不到時，先在範圍內升級 yt-dlp：`setup-venv.ps1 video-downloader -Force`。
- GUI 的 API 只聽 127.0.0.1，寫入請求要帶 `X-Video-Downloader: 1`，「開啟位置」只限下載資料夾或下載過的檔案。
- 只做通用下載：不針對特定網站寫破解或繞過存取限制的程式，DRM 內容不支援。
