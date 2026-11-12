# 樹狀圖輸出格式（tree-*）

擁有者的要求：樹狀圖有很多做法（Markdown、Flow Chart、XMind…），輸出層要像 adapter pattern 一樣可以換。
實作在 [`video_notes/adapters/render_tree.py`](../video_notes/adapters/render_tree.py)；五種格式共用同一棵樹，
只差「怎麼寫出去、怎麼跳脫」。可折疊 HTML（`tree-html`）走 HTML 範本（見 `render_html.py`），不在這份。

> 查證說明（2026-11-12）：下面「來源」只讀文件，沒有下載或執行任何東西。XMind 官方沒有公開 `.xmind` 內部格式的規格，
> **content.json 的欄位是從社群工具與 SDK 說明拼起來的，尚未用真正的 XMind 程式打開驗證**——請擁有者拿一個
> `outputs/*.xmind` 在 XMind 裡開一次（見最底下「待驗證」）。

## 結論（推薦給使用者的預設）

| 用途 | 推薦 | 為什麼 |
|---|---|---|
| **預設** | `tree-md`（Markdown 清單） | 純文字、Notion 貼上就是樹、任何地方都看得到；不需要任何軟體 |
| 想在 XMind 裡編輯 | `tree-xmind`；打不開就換 `tree-opml` | `.xmind` 是原生格式（保留備註、折疊）；OPML 是 XMind 官方列出的匯入格式，最保險 |
| 想要「圖」而不是清單 | `tree-html`（單檔、可折疊、離線） | 瀏覽器直接看，不依賴外部服務 |
| 要放進 GitHub／文件網站 | `tree-mermaid` | GitHub、很多 Markdown 渲染器內建 mindmap |
| 用 FreeMind／Freeplane | `tree-freemind` | 它們的原生格式 |

## 樹的結構（所有格式一致）

- 根 = `analysis.title`（沒有就用 `summary`）。`summary`＋`overview` 當根的備註。
- 子節點 = `sections`（遞迴 `children`，最多 8 層防呆）；每個 section 的 `points` 是葉子，`summary` 是備註。
- `kind=collection`：多一個「**來源影片**」分支（每支影片一個節點，網址是 http/https 才附連結）。
- 另外加四個分支（有內容才出現）：**重點**（key_points）、**名詞**（term → 下一層是解釋）、**行動**（actions）、**注意**（caveats）。
  判斷：這些是使用者拿到樹狀圖後最常想「一眼看到」的東西，成本只是多幾個節點；
  沒加的有 `timeline`（它本來就是線性的，放進樹反而打散）、`quotes`、`perspectives`、`tags`（想要的話之後再加，樹的建構只有一處）。
- `layout_hint.tree_depth`（1～6，預設 3）= 預設展開層數：根算第 0 層，第 `tree_depth` 層以下有子節點的節點會折疊。
  只有 FreeMind（`FOLDED`）與 XMind（`branch: folded`）支援，其餘格式忽略。
- 標題太長會截斷（Markdown 500、OPML／FreeMind 160、XMind 120、Mermaid 100 個字元，加「…」）；
  截斷發生在跳脫**之前**，不會切壞跳脫序列。支援備註的格式（OPML、FreeMind、XMind）會把完整文字放進備註。

## 各格式

| 名稱 | 副檔名 | 備註 | 折疊 | 連結 | Notion 能直接顯示？ |
|---|---|---|---|---|---|
| `tree-md` | `.md` | 有（斜體子項） | 無 | 有 | **能**：貼上就是巢狀清單；匯入 .md 也行 |
| `tree-mermaid` | `.mmd` | 無 | 無 | 無 | 能，但要貼進 Notion 的 `/code` 區塊並選 Mermaid 語言才會畫成圖（Notion 的 Mermaid 預覽是否支援 mindmap 取決於它內建的 Mermaid 版本，未驗證） |
| `tree-opml` | `.opml` | 有（`_note`） | 無 | 有 | 不能（要先用大綱／心智圖軟體開） |
| `tree-freemind` | `.mm` | 有（richcontent） | 有 | 有 | 不能 |
| `tree-xmind` | `.xmind` | 有 | 有 | 有 | 不能 |
| `tree-html` | `.html` | 範本決定 | 範本決定 | 範本決定 | 不能（可以匯出圖片再貼） |

### Markdown 清單（`tree-md`）
- 優點：最通用；Notion、Obsidian、GitHub 都吃；XMind 也能匯入 Markdown。缺點：只是清單，沒有圖。
- 跳脫：反斜線跳脫 `` \ ` * _ [ ] < > | ~ ``；行首的 `# + - ! > =` 與「數字＋.」也跳脫（否則會變成標題／清單）；
  看起來像 HTML 實體的 `&xxx;` 跳脫 `&`。連結網址的括號、空白用百分比編碼。
- XMind 的 Markdown 匯入吃標題結構（`#` 中心主題、`##` 主要主題…），我們輸出的是 `#` 根＋巢狀清單，
  清單是否會被轉成子主題官方頁沒寫清楚，**要在 XMind 匯入時才能確定**；要進 XMind 請優先用 OPML／.xmind。

### Mermaid mindmap（`tree-mermaid`）
- 語法：第一行 `mindmap`，之後靠**縮排**決定階層（官方：只和上一行比較相對縮排；不明確時掛在最近一個縮排較少的節點）。單一根。
- 節點形狀：`id[文字]`、`id(文字)`、`id((文字))`…；markdown 字串 `` id["`**粗體**`"] ``。
- **官方 mindmap 頁沒有寫跳脫規則。** 我們的做法：每個節點都用「`id["…"]`」（根用 `root(("…"))`）、
  id 用程式產生的 `n1`、`n2`…（不用使用者文字當 id），文字裡 `#` `"` `<` `>` `&` `` ` `` `%` `\` 一律轉成 Mermaid 的 `#35;`、`#quot;`、`#lt;`…
  實體碼（flowchart 文件載明 `#code;` 做法，且 `#35;` 可寫出字面的 `#`；mindmap 共用同一個實體前處理，**未在 mindmap 上實測**）。
  換行改空白。
- 缺點：沒有備註、折疊、連結；節點太多時版面會擠。

### OPML 2.0（`tree-opml`）
- 最小合法結構：`<opml version="2.0"><head>…</head><body><outline text="…"/></body></opml>`；
  `head` 子元素全是選填，`body` 至少一個 `outline`，`outline` 可有任意屬性、可巢狀。
  `text` 是約定俗成的必備屬性；`_note` 放備註、`type="link" url="…"` 放連結（OPML 2.0 慣例）。
- 優點：XMind、Obsidian 外掛、各種大綱軟體都吃，格式最簡單。缺點：沒有折疊、版面資訊。
  XMind 匯入時是否保留 `_note` 沒有查到官方說法。
- 跳脫：交給 `xml.etree`（`& < > "` 與換行），先剝掉 XML 1.0 不允許的控制字元與孤立 surrogate。

### FreeMind .mm（`tree-freemind`）
- 最小結構：`<map version="1.0.1"><node TEXT="…"/></map>`，`node` 巢狀。FreeMind wiki 寫「FreeMind 不寫 XML 宣告」，
  但帶宣告也能讀；我們有寫 `<?xml version='1.0' encoding='utf-8'?>`。
- 屬性：我們用 FreeMind 實際檔案慣用的大寫 `TEXT`、`LINK`、`FOLDED="true"`（wiki 頁列的是小寫，未在 xsd 確認；
  真實的 .mm 檔都是大寫，所以採大寫）。備註 = `<richcontent TYPE="NOTE"><html><head/><body><p>…</p></body></html></richcontent>`。
- 優點：有折疊、備註、連結；XMind、Freeplane、MindManager 等都能匯入。缺點：較舊的格式。

### XMind .xmind（`tree-xmind`）
- 結構：ZIP（**根目錄不能再包一層資料夾**，XMind SDK 說明明寫「Don't include top level folders」），內含
  `content.json`、`metadata.json`、`manifest.json`（有縮圖 `Thumbnails/thumbnail.png` 的是選配，我們不放）。
- `content.json` = 工作表陣列：`[{"id", "class":"sheet", "title", "rootTopic": {...}}]`；
  主題 `{"id", "class":"topic", "title", "children":{"attached":[…]}, "notes":{"plain":{"content":"…"}}, "href":"…", "branch":"folded"}`。
  `rootTopic.structureClass` 用 `org.xmind.ui.map.clockwise`。社群說明提到 topic 要有 `class:"topic"`、sheet 要有 `class:"sheet"`。
- `manifest.json` = `{"file-entries": {"content.json": {}, "metadata.json": {}}}`；
  `metadata.json` = `{"dataStructureVersion":"2","creator":{name,version},"layoutEngineVersion":"3","activeSheetId":…}`。
- **舊版 `content.xml`**：XMind 8 以前用 `content.xml`／`meta.xml`／`META-INF/manifest.xml`；新版（Zen／2020 以後）讀 `content.json`。
  社群工具的讀取流程是「先找 content.json，沒有才退回 content.xml」。有些社群寫入程式會同時放一個 content.xml 當相容殼，
  但**沒有資料說新版 XMind 需要它**，所以我們不放（只放 content.json）。這點屬於「待驗證」。
- id：用固定命名空間的 UUID5 產生，同樣輸入得到完全相同的位元組（zip 時間戳也固定），方便測試與比對。
- 優點：XMind 原生，備註／折疊／連結都保留。缺點：沒有官方規格，XMind 改版可能壞；所以保留 OPML 當備案。

### 可折疊 HTML（`tree-html`）
走 `templates/tree.html`（單檔、離線、不載入外部資源），資料用 `<script type="application/json" id="vn-data">` 注入，
由範本用 `<details>` 或 JS 畫出來。見 `render_html.py`。

## XMind 能匯入什麼
官方使用者指南（import 頁）列出可匯入：**FreeMind、Markdown、OPML**，另有 MindManager、MindNode、MindMaster、
Word（僅 .docx）、TextBundle 等。Markdown 匯入路徑：桌面版「≡ → File → Import → Markdown」，網頁版可上傳或貼上文字。
（搜尋摘要沒有顯示哪些匯入需要付費方案，未確認。）

## 來源
- XMind 概述與檔案結構（社群彙整）：https://en.wikipedia.org/wiki/XMind
- XMind 匯入說明：https://xmind.com/user-guide/import-new 、Markdown：https://xmind.com/help/import-markdown-file-windows
- XMind SDK（Dumper 輸出要 zip、不可有頂層資料夾；manifest 更新）：https://github.com/xmindltd/xmind-sdk-js
- 社群的 .xmind 讀寫工具（content.json 為主、content.xml 為舊版、topic／sheet 的 class 欄位）：
  https://glama.ai/mcp/servers/@apeyroux/mcp-xmind/blob/27b49854805b2b536b82acb0420de9b57a03e87f/CLAUDE.md 、
  https://glama.ai/mcp/servers/@Master-Frank/XmindMcp/blob/9fd40aea50dba6ba8b3a4a3c104a9ee6461c2051/xmind_writer.py
  （這兩頁在查證時內容沒載入，只取到搜尋摘要；欄位細節的另一部分來自撰寫者對 XMind Zen 檔案的既有認識，因此列為待驗證）
- Mermaid mindmap：https://mermaid.js.org/syntax/mindmap.html ；實體碼與引號：https://mermaid.js.org/syntax/flowchart.html
- OPML：https://en.wikipedia.org/wiki/OPML ；規格 https://opml.org/spec2.opml（查證時只拿到導覽，沒有取得全文）
- FreeMind 檔案格式：https://freemind.sourceforge.io/wiki/index.php/File_format

## 待驗證（需要有 XMind／Notion 的電腦）
1. 用 XMind 打開 `outputs/<slug>.tree-xmind.xmind`：能開、備註與折疊正常。打不開 → 優先試補一個最小 `content.xml`，其次改推薦 OPML。
2. 用 XMind 匯入 `.opml`、`.mm`、`.md`，確認階層與備註保留。
3. Notion 貼 Mermaid mindmap 是否畫得出來。
