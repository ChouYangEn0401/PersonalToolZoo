# 📖 Novel Reader

> 把小說（或任何長文）唸給你聽：貼上文字或開啟 .txt，邊聽邊看大字幕，像 KTV 一樣跟著目前這一段走。

整併自兩個舊專案：「My Internet Novel Reader」的 GUI 朗讀器，以及「My Voice Assistant」（它只是一支用 Google 語音念固定句子的小程式，現在變成這裡的第二種語音引擎）。

## 功能

- **兩種語音引擎**
  - Windows 內建語音（離線、免費、幾乎不用等）：自動選台灣中文的聲音（例如 Microsoft Hanhan），也可以換成其他已安裝的聲音。
  - Google 語音（需要網路，比較自然）：中文（台灣）或英文。
- **語速** 0.6～3 倍。內建語音用 SAPI 原生的語速；Google 語音用 ffmpeg 的 atempo 變速不變調（沒有 ffmpeg 就是原速）。
- **邊播邊產生**：只預先產生後面 3 段，按下播放幾乎馬上開始（舊版要先把全文轉完才開始播）。
- 段落清單跟著播放移動，雙擊任一段從那裡開始；可以刪除不想聽的段落；暫停 / 繼續、上一段、下一段。
- 太長的段落會在句尾（。！？；…）切開，不會切在「...」中間。
- **記住讀到哪裡**：同一個 .txt 再開一次，會跳到上次讀到的段落。
- 開檔自動判斷 UTF-8 / Big5 / UTF-16 / GB18030。

## 使用方式

以下在 PersonalToolZoo repo 根目錄執行：

```powershell
.\scripts\setup-venv.ps1 novel-reader
.\tools\novel-reader\.venv\Scripts\python.exe tools\novel-reader\NovelReader.py
.\scripts\build.ps1 novel-reader
```

---

## 交接

| 項目 | 內容 |
|---|---|
| 入口 | `NovelReader.py`（畫面）；核心在 `reader/`：`segments`（分段）、`tts`（語音引擎）、`player`（邊播邊產生） |
| 版本號 | `version.py` 的 `__version__` → exe 檔名 `NovelReader(vX.Y.Z).exe`、視窗標題 `Novel Reader vX.Y.Z` |
| 環境 | 有第三方套件 → `tools\novel-reader\.venv` |
| 依賴 | `pywin32<400`（SAPI）、`pygame<3`（播放）、`gTTS<3`（Google 語音）；Google 語音加速另外需要系統的 ffmpeg |
| 打包額外內容 | `hiddenimports`: `win32com.client`、`pythoncom` |
| 測試 | `.\tools\novel-reader\.venv\Scripts\python.exe -m unittest discover -s tools\novel-reader\tests -v`（7 個：分段、SAPI 連續產生、播放流程；pygame 用 dummy 音效驅動，不會出聲） |
| Release tag | `NovelReader_vX.Y.Z` |

### 注意事項

- **不要改回 pyttsx3**：pyttsx3 2.99 在 Windows 上第二次 `runAndWait()` 就永遠卡住（主執行緒、背景執行緒都一樣，2026-10-05 實測）。
  `reader/tts.py` 直接用 SAPI 的 `SpVoice` + `SpFileStream`，同步產生 WAV。
- SAPI（COM）物件只能在建立它的執行緒使用：引擎由 `player` 的產生執行緒建立與關閉。
- 舊版的其他問題已修掉：關視窗時 `root.destroy()` 被呼叫兩次而丟例外、暫存資料夾沒有 `parents=True`
  （新電腦第一次執行就崩潰）、加速檔的路徑少了分隔符、生成全部段落時畫面卡住。
- 沒有帶過來的：舊專案的 `main.py` 是針對單一小說網站、用 Playwright 抓章節的命令列實驗
  （多個指令寫著「not develop yet」），不是通用功能，原始碼留在 `chore(novel-reader): import …` 那個 commit。
  `requirements.txt` 原本也漏列了 playwright、pygame、pyttsx3。
