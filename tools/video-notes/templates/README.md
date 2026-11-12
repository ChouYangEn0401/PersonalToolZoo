# Video Notes 的 HTML 輸出範本

AI 只產生 `analysis.json`（格式見 [`docs/analysis-schema.md`](../docs/analysis-schema.md)）；程式把 JSON 塞進這裡的範本，
範本自己用 JavaScript 把畫面畫出來。**AI 不寫 HTML**，所以版面穩定、換範本不用再花分析的 token。

## 有哪些範本

| 檔案 | 長相 | 適合 |
|---|---|---|
| `sheet.html` | 一小張卡片：一句話結論、最多 7 個重點、各段一句話、標籤；其他欄位只放前幾項（放不下的寫「＋另外 N 項」） | 短影音、新聞快訊、想一眼看完的內容 |
| `longform.html` | 長文：左側目錄（窄螢幕收合在頂端）、段落依層級展開，時間軸／名詞／行動清單／金句／各方說法／注意事項各成一區 | 一般長度的影片、訪談、財經節目；要印出來或從頭讀到尾 |
| `tabs.html` | 多分頁：「總覽」＋每個最上層段落一頁＋「附錄」（時間軸、名詞、金句、來源）；子主題可收合；分頁記在網址 `#tab=…` | 長課程、主題很多的內容、多支影片合併（課綱式：大主題 → 慢慢展開） |
| `tree.html` | 可折疊的樹：根是標題、段落是分支、條列重點是葉子；寬螢幕可切「心智圖／大綱」，窄螢幕與列印是縮排大綱 | 想先看整體架構、複習用 |

`layout_hint.template` 只會是 `sheet`／`longform`／`tabs`（AI 依內容建議）；`tree` 是另外選的輸出形式，
預設展開到 `layout_hint.tree_depth` 層（根算第 0 層，`tree_depth = 2` 表示看得到兩層段落）。

`tree.html` 只畫 `title`、`summary`、`tags` 與 `sections` 樹；時間軸、名詞等欄位請用另外三個範本看。

## 資料契約（Python 端照這個填）

1. 每個範本是**單一檔案**，CSS／JS 全部寫在檔案裡，不載入任何外部資源（檔頭有 CSP 把外部載入整個擋掉）。
2. 檔案中**恰好一處**：

   ```html
   <script type="application/json" id="vn-data">__VN_DATA__</script>
   ```

   把 `__VN_DATA__` 換成 JSON 文字。**JSON 裡的 `<` 必須先換成 `<`**，資料才不會提早結束這個 script 區塊。
   用字串取代（`str.replace`），不要用 `re.sub`（它會把 JSON 裡的反斜線當成跳脫符號）。
3. JSON 的結構：

   ```json
   {
     "analysis": { "…analysis.json 的全部欄位…": "" },
     "meta": {
       "profile_name": "📰 新聞快訊",
       "modifier_names": ["⏱ 時間軸"],
       "tool_version": "2.1.0",
       "generated_at": "2026-11-12T20:00:00"
     }
   }
   ```

4. 範本怎麼處理資料（改範本或寫新範本時必須維持）：

   | 項目 | 行為 |
   |---|---|
   | 文字 | 一律當純文字：只用 `textContent`／`createElement` 放進畫面，不把資料組成 HTML、不執行資料 |
   | 連結 | 只有 `http:`／`https:` 開頭的網址才變成連結（`rel="noopener noreferrer" target="_blank"`）；其他照原樣顯示成文字 |
   | 時間 | 秒數或 `null`；顯示 `mm:ss`，超過一小時 `h:mm:ss`。`sources` 只有一筆而且是 YouTube 時，時間可以點了跳到那一秒；其他情況只是文字 |
   | 缺欄位、空陣列、型別不對 | 那個區塊整個不顯示，不會留空標題 |
   | `quality_flags` 含 `schema_repair_failed` | 頁首提醒「這份是降級結果，內容可能不完整」（`transcript_low_confidence`、`truncated_input`、`member_missing` 也各有一句提醒） |
   | `kind` 是 `collection` | 頁首列出各來源影片 |
   | 頁尾 | 「由 Video Notes {tool_version} 產生於 {generated_at}・方案 {profile_name}」 |
   | 還沒填資料（`__VN_DATA__` 原樣） | 顯示「這是範本，沒有資料」 |
   | JSON 壞掉或沒有 `analysis` | 顯示「讀不到筆記資料」與怎麼處理，不會是空白頁 |

## 範例資料（`samples/`）

| 檔案 | 內容 | 用來看什麼 |
|---|---|---|
| `video-news.json` | 4 分鐘的新聞快訊，單一 YouTube 來源 | `sheet`；時間可點 |
| `video-course.json` | 1 小時 32 分的課程，段落最深 4 層，欄位幾乎全滿 | `tabs`、`longform`、`tree`；`h:mm:ss` |
| `collection.json` | 三支影片合併；**故意放了惡意字串** | 安全檢查：標題含 `<script>alert(1)</script>`、一個來源網址是 `javascript:alert(1)`、一條 300 個數字、沒有空白的字串、標籤與名詞裡有 HTML 標籤。頁面上應該全部看得到原文、不會跳出任何視窗、不會出現水平捲軸 |

三份都通過 `video_notes.analysis.validate()`。測「降級結果」時把任一份的 `quality_flags` 加上 `"schema_repair_failed"`。

## 預覽

沒有預覽腳本：用 Python 把範例填進範本、存成 `.html`，再用瀏覽器打開。在 `tools\video-notes\` 底下：

```python
import json, pathlib

tpl = pathlib.Path("templates")
data = json.loads((tpl / "samples" / "video-course.json").read_text(encoding="utf-8"))
text = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
html = (tpl / "tabs.html").read_text(encoding="utf-8").replace("__VN_DATA__", text)
pathlib.Path("data").mkdir(exist_ok=True)
pathlib.Path("data/preview-tabs.html").write_text(html, encoding="utf-8")
```

存在 `data\`（不進版控）。直接打開範本本身（還沒填資料）會看到「這是範本，沒有資料」，這是正常的。

## 自己改範本

把**同名檔案**放到工具旁的 `data\templates\`（原始碼執行是 `tools\video-notes\data\templates\`，
打包的 exe 是 exe 旁邊的 `data\templates\`），就會蓋過內建的；刪掉就回到內建版本。

改的時候注意：

- 保留那一行 `id="vn-data"` 的 script，而且 `__VN_DATA__` 在整個檔案只能出現一次（註解裡也不要寫）。
- 四個範本的 `<style>` 與 `<script>` 前半段是**完全相同的共用部分**（有「VN 共用樣式／共用程式」的註解標出頭尾）：
  顏色變數、字級、各種區塊的畫法都在那裡。要改共用部分就四個檔一起改，四個範本才會維持同一個樣子。
- 顏色只改 `:root` 的變數（下面緊接著深色主題的那一組）。
- 不要加外部資源（字型、圖片、CDN 腳本）；檔頭的 CSP 會擋掉，而且這些頁面要能離線打開。
- 資料只能用 `textContent` 放進畫面（共用程式的 `VN.el(tag, class, text)`），不要用 `innerHTML`。
