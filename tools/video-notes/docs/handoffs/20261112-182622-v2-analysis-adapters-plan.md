# Video Notes v2：分析暫存 + 可換的 adapter + 多片合併 + 多種輸出

- **狀態：已修**（2026-11-12，`dev/video-notes` 併進 master；merge commit `d47f868`，驗收結果見檔尾「收尾紀錄」）
- 建立：2026-11-12 ｜ 範圍：`tools/video-notes/`（必要時 `libs/toolzoo/`）
- 開發線：`dev/video-notes`（remote 有；本機沒有就 `git switch -c dev/video-notes origin/dev/video-notes`），開工前 `git merge master`
- 下一個 session 只要使用者說 **continue**：讀完這張，從「## 執行計畫」的第 0 波開始，照做。

## 擁有者原話（一字不改）

> 我有一個工具可以下載video，然後轉換成字幕，在轉換成 notion。
> 我想要你幫我把這個軟體優化一下。目前覺得他的內建 stt 有點爛，有點在想要不要乾脆讓他用好一點的 ai-model 來處理？
> 然後我也覺得單純只整理出文字彙總筆記好像很普通，感覺OK的話(使用者願意燒token的話)整理成小份的 artifact 也可以。然後我也覺得可以幫別人整理出樹狀圖的結構，整理很多資訊。
>
> 另外是，我覺得之前都只能一片一片錄影。
> 但我會希望可以直接，好幾片一起來，例如，電影講說、例如上課筆記講自製作、新聞快訊總結、...，我都會覺得這會非常方便好用 !!

> 好，首先我直接评论你的架构。你讲的没有错，基本上就是原本的架构我都已经写出来，它可以同时批次下载很多，甚至是未来我可能会想要把不同片源的这种下载方式也把它加进去，所以前面的架构你要先清楚，反正就是下载阶段，然后接下来是理论上是每一片影片会自己去整理出一份自己的笔记，这个没有问题。然后这边也跟你说的一样，就是我会希望到时候需要的时候是把好几个影片可以把它合 在一起。所以其實每一每一個影片他都會有自己的筆記，只是最後透過這樣的方式把它串連在一起。
>
> 然後你說的那些模式確實就是我跟你說的模式，我也覺得可以給別人選出模式。因為這樣子的話在使用上可能會更加的便利，他會直接知道他要的模式來用，那樣透過模式我們可以去指定更好的prompt也許效果會更好。
>
> 然后再来是关于你说那个 STT 的部分，就是我确实是觉得，当然本地要先能够跑，所以原则上本地的这个东西当然没有必要删掉。所以我的概念一直以来都是 adapter 那种感觉，你应该是要让我本地可以跑，然后我需要换更好的时候，我可以换成不同服务商的这种架构，然后让这个东西是可以很方便去做切换的。
>
> 然后我觉得关于输出模式的话，基本上就是感觉可以先让 Fable 做几个比较简单的范本，然后这些范本就是专门用来整理不同的资料的，然后可能有一小张 sheet 的，就是很简单呈现内容就好，然后还有针对很长的内文去做的，甚至是做里面有带有 tab 的，那就是变成说可能很大范围的内容，像课纲这种可以用一个大主题这样慢慢把它呈现下去，等于说就是先请 Fable 设计几种范本，然后到时候在做的时候直接让 Sonnet 去里面去填里面的资料，其实这样应该会很简单很方便。然后树状图的话，当然做法有很多，有人会用 Markdown， 有人会用什么 Flow Chart， 那我觉得方法有很多，那我是觉得你可以去上网搜寻一下，还有另一个工具是叫 Xmind，然后它上面所做出来的流程图好像也很漂亮，然后前一阵子好像发现它是可以输出来的，所以理论上你应该是可以吃到格式。反正这边的概念也是一样，你输出流程图的时候，它同样应该是要有一个像 adapter pattern 这类的东西，然后它可以更换不同的模式。然后我觉得这边比较特别的点是，我之前就是一个流程跑下去就结束，但我觉得之后应该要把 UI 改得更方便，就是说我同一个影片可能处理过了，但是我丢进去以后，我可以让它重新生成一遍，或者是跟其他片一起去整理出一个很大份的，就是包含我今天讲的内容。然后再来就是你每一次影片分析出来了以后，应该要先有一个暂存起来，然后未来我想要输出其他模式，例如说树状图，或者是输出其他种形式的树状图，或者是生成一张图片等等，我觉得就可以反复利用这个东西，而不是说它是一个抛弃式的。所以我觉得这边的架构可以再多增加一点点的弹性，让我未来可以就是更方便去生成不同的形式的这种资料。
>
> 所以原则上，基本上整个架构大概是这样。那你提的问题基本上不是很重要，所以就是反正一定是我要转换，一定是要上传，所以这就没什么好讲的。至于你说好几篇一起的话是哪一种整理方式，我觉得这个东西就是要让 agent 自己去决定。然后我刚才有讲了嘛，你那个模式本身就已经有点像是让使用者已经先选定了一个 type， 所以这个 type 一定会影响最后的 artifacts 的生成的这个状况。所以你这边前后已经锁定的情况下，然后让 AI 在做整理的时候自己微调这个形式，我觉得其实整个整理出来就会干净很多，甚至是未来也还不止可以只有输出这几种模式，像你如果要输出 PPT 或者是输出 Word 档，感觉起来也可以用这种方式跟架构去把它做出来，或者是说单纯就是把资料整理完，然后让那个 Cloud 里面的 Skills 直接去来做也可以。等于说这边重点是你要把资讯整理出很干净的样子，那这样未来它要调用什么工具其实都会很方便。
>
> 我目前的想法是这样了，我觉得你可以先理解一下我整个脉络，然后 enhance prompt 一下，然后我觉得你可以想一下这个任务大概适合让谁来做，然后你就可以丢给 sub agent 来做。然后我个人觉得有些东西应该是可以分段开发的，所以你可以让很多个 sub agent 一起来做事情。
>
> 不过有鉴于我现在的 token 用量其实有点多，可能会不太够用，所以目前是希望你先暂时写出来，就是我现在要你整理嘛，你就先把你整个脉络写出来，有点像是把整个 prompt 重新把它打出来给我一遍。那这样下一次我跟你回复这个对话的时候，我只要用 continue 之类的东西，就会按照你现在整理出来的这个规划，呼叫很多 sub agent 去做，然后就是等于说你就直接帮我思考下一次我如何透过 continue 就直接把东西开发完，因为我现在 token 应该不会想要立刻来做这个专案。

## 問題一句話

Video Notes 現在是「一條流程跑到底就丟掉」：語音辨識只有本機 Whisper、每支影片只產出一份 Markdown、多支影片彼此不相通。
要改成「每支影片分析一次、存成乾淨的結構化資料，之後想轉成什麼形式都重複利用」。

## 設計決定（擁有者已拍板，不要再問）

1. **管線分四層，每層都是 adapter**（本機能跑是底線，換服務商只改設定）：

   ```
   來源(Source) → 語音辨識(STT) → 分析(Analyze) → 輸出(Render/Export)
   yt-dlp(現有)   local-whisper    每片一份         markdown / 樹狀圖 / HTML 範本 /
   未來:其他片源   雲端(OpenAI/Gemini) analysis.json   xmind / pptx / docx(未來)
   ```
2. **`analysis.json` 是核心資產**（放在每支影片資料夾，與 notes 並列）：
   模式(profile)＋AI 依內容微調後的結構化結果——標題、一句話結論、章節/主題樹、重點、
   時間軸、名詞、行動項目、來源資訊、schema 版本號。輸出層**只讀它**，不碰逐字稿；
   重做輸出不用再花分析的 token。要重新分析才重呼叫 AI。
3. **模式(type)＝使用者先選的 profile/preset**（現有的 knowledge/news/quick/finance/podcast…），
   它決定分析 prompt 與預設輸出形式；**AI 在這個框架內自己微調形式**（例如決定用幾層樹、要不要時間軸）。
4. **多片合併(Collection)**：吃多份 `analysis.json`（不是逐字稿）→ 產出一份同 schema 的合併 `analysis`，
   存在輸出資料夾的 `collections/<時間>-<slug>/`。合併「怎麼整理」交給 AI 依模式決定
   （新聞→依事件去重歸類；課程→依課綱排序；電影解說→連貫敘事）。每支影片自己的筆記照舊保留。
5. **輸出範本**：先請 **Fable** 設計幾個 HTML 範本（單檔、無外部依賴、可明暗主題），
   **Sonnet（或使用者選的模型）只輸出符合 schema 的 JSON 資料去「填」**，程式把 JSON 塞進範本——
   AI 不寫 HTML，省 token、版面穩定。範本三種起手：
   - `sheet`：一小張，簡單呈現
   - `longform`：長文，有目錄
   - `tabs`：多分頁，大範圍內容（課綱式：大主題 → 慢慢展開）
6. **樹狀圖也是 renderer adapter**：markdown 巢狀清單（貼 Notion）、Mermaid mindmap、可折疊 HTML、
   OPML／FreeMind `.mm`（XMind 能匯入）、`.xmind`（XMind 是 zip + `content.json`，要上網查現行格式再做）。
   「上網查有哪些做法」是第 1 波的明確任務。
7. **UI 要能「回頭再加工」**：筆記庫裡選一支或多支 → 重新分析 / 換輸出形式 / 合併成大份；
   丟進已處理過的網址不再只是「沿用/重做」彈窗，而是直接進「這支影片現有什麼、要再產生什麼」。
8. **未來輸出（PPT／Word／圖片）不在本期做**，但 `analysis.json` 要乾淨到可以直接交給 Claude 的 skills（pptx／docx）。
   本期只要把 Renderer 介面留好。
9. 雲端 STT 一定要上傳音訊——擁有者已接受，不用再問。金鑰走 `.env`（既有機制）。

## 執行計畫（continue 之後照這個做）

**硬限制**（全域規則）：同時最多 5 個背景 agent；這台電腦不跑重負載、不開網路埠測試（連線／雲端一律用假的 adapter 測）；
不跑 Unity；測試離線、不打真的 API。每個 agent 只改自己負責的檔案（見下表），不要互相蓋。
工作在 `dev/video-notes`，一個主題一個 commit，完成後回 master `git merge --no-ff dev/video-notes`（merge 訊息寫做了什麼、為什麼）。

### 第 0 波：契約（主 session 自己做，不派 agent，一個 commit）
- 切到 `dev/video-notes`、`git merge master`、先跑一次現有測試確認基線（`tools/video-notes/tests`）。
- 寫三份**介面契約**（只有型別與空殼，不含實作）：`video_notes/analysis.py`（schema＋讀寫＋版本）、
  `video_notes/adapters/`（`stt.py`、`render.py`、`source.py` 的 Protocol／註冊表）、
  `docs/analysis-schema.md`（欄位說明＋範例 JSON）。**後面所有 agent 都依賴這三份，所以要先定死。**
- 現有行為不變：把現在的 Whisper 與 yt-dlp 包成第一個 adapter 即可。

### 第 1 波：平行（5 個 agent，彼此檔案不重疊）
| agent | 模型 | 任務 | 擁有的檔案 |
|---|---|---|---|
| A STT | sonnet | 雲端 STT adapter（OpenAI `gpt-4o-transcribe`、Gemini 音訊）＋長音訊切段＋時間碼接回＋設定欄位；本機 Whisper 保持預設 | `adapters/stt_*.py`、`transcribe.py`、對應 tests |
| B 分析 | sonnet | 把 `summarize.py` 拆成「產 `analysis.json`」＋「由 analysis 出 Markdown」；pipeline 多一個 analyze 階段與快取／重做規則；舊的 notes 檔仍要產得出來 | `analysis.py`、`summarize.py`、`pipeline.py`、tests |
| C 範本 | **fable** | 設計 `sheet`／`longform`／`tabs` 三個 HTML 範本＋範例資料 JSON（吃 `analysis-schema.md`），明暗主題、手機寬度可讀、單檔無外部依賴 | `templates/*.html`、`templates/samples/` |
| D 樹狀圖 | sonnet | **先上網查**：Mermaid mindmap、OPML、FreeMind `.mm`、`.xmind` 現行格式、XMind 匯入匯出；再實作各 renderer＋在 XMind 之外至少用文字檢查輸出正確 | `adapters/render_tree_*.py`、tests；查到的結論寫進 `docs/tree-formats.md` |
| E 模式 | sonnet | 新增 preset／profile：`news-roundup`、`course`（課程合集）、`movie-recap`，以及給「合併」用的 prompt；每個模式標明預設輸出形式 | `prompts/**` |

### 第 2 波：平行（依賴第 1 波）
| agent | 模型 | 任務 | 擁有的檔案 |
|---|---|---|---|
| F 合併 | sonnet | Collection：多份 analysis → 合併 analysis；token 用量預估（使用者願意燒才做，所以先估再確認）；CLI `--combine` | `collection.py`、`cli.py`、tests |
| G 輸出 | sonnet | HTML renderer：讓 AI 只輸出符合 schema 的 JSON，驗證後填入 C 的範本；失敗時降級成 Markdown | `adapters/render_html.py`、tests |
| H UI | sonnet | 筆記庫多選、重新分析、換輸出形式、合併；已處理影片的新流程；輸出形式／STT 服務的下拉選單 | `web/**`、`jobs.py` |

### 第 3 波：收尾（主 session）
- 整合測試（假 STT、假 LLM）、`python -m unittest`／pytest 全跑。
- 更新 README（含新增選項與「交接」段落）、`docs/analysis-schema.md`、`docs/HANDOFF.html`、`docs/OPEN_ISSUES.md`。
- `scripts\build.ps1 video-notes`（先設 `$env:TOOLZOO_NO_BROWSER = 1`）過冒煙測試；會在桌面跳視窗，**開始前先跟使用者說一聲**。
- 改到 `libs/` 的話，其他用 libs 的工具也要重 build（見 AGENTS.md）。
- 回 master `git merge --no-ff dev/video-notes`，把這張的狀態改成「已修」並寫 merge commit；`git status` 乾淨。**不 push、不打 tag，除非使用者說。**

### 給每個 sub agent 的共同 brief（派工時貼進去）
> 你在改 PersonalToolZoo 的 `tools/video-notes/`。先讀 `AGENTS.md`、本檔、`docs/analysis-schema.md`、`video_notes/__init__.py`。
> 只改你被指定的檔案；介面以第 0 波的契約為準，要改契約先回報不要自己改。測試離線、不打真的 API、不開網路埠、不跑重負載。
> 中文 Windows 路徑的檔案用 Edit／Write，不要用 heredoc。完成後回報：改了哪些檔、跑了哪些測試與結果、沒做完的事。不要 commit（由主 session 統一 commit）。

## 驗收
- 同一支影片：處理一次後，不重呼叫 AI 就能輸出 Markdown、三種樹狀圖、三種 HTML 範本。
- 選 2 支以上影片可合併成一份總筆記，各支原本的筆記不受影響。
- STT 在設定裡可切本機／雲端；沒金鑰或雲端失敗時清楚報錯，且本機路徑完全不受影響。
- 舊資料夾（只有 notes、沒有 analysis.json）仍能正常開啟，不用遷移。
- 測試全過、`build.ps1 video-notes` 冒煙測試 OK、`git status` 乾淨。

## 不要做的事
- 不要讓 AI 直接寫整頁 HTML（只填 JSON）。
- 不要刪掉本機 Whisper 或改掉它的預設地位。
- 不要在這台電腦開網路埠、跑雲端真實呼叫的自動測試、或一次開超過 5 個 agent。
- 不要把金鑰、個人資料寫進 repo（repo 是公開的）。
- PPT／Word／圖片輸出本期不做，只留介面。
- 不要自己 push／打 tag／發版。

## 還沒決定、但不阻擋動工的小事（agent 自己用建議值，回報時註明）
| 項目 | 建議（預設照做） |
|---|---|
| 雲端 STT 預設服務 | OpenAI `gpt-4o-transcribe`；Gemini 當第二個 |
| 合併前是否先顯示 token 預估 | 是，超過門檻才要使用者確認 |
| 範本放哪 | `tools/video-notes/templates/`，使用者可在 `data/templates/` 覆蓋（同 prompts 的規則） |

## 收尾紀錄（2026-11-12）

照上面的四波做完，並把同資料夾三張 `suggest-*` 一起收掉。merge commit：`d47f868`（Merge dev/video-notes: Video Notes v2 …）。

| 波 | 做了什麼 | commit（dev/video-notes） |
|---|---|---|
| 0 | 契約：errors.py、analysis.py（schema v1）、adapters 的 Protocol 與登記表、collection 簽名、naming、config、docs/analysis-schema.md；library.py | 79c207e、56294a4、c941a5e |
| 1 | 錯誤合約落實＋health＋doctor（S）、語音辨識 adapter＋openai-compat（A）、樹狀圖與 HTML 輸出（D）、Fable 的 4 個範本（C）、analyze＋Markdown 輸出＋pipeline（B） | abcc53b、35cd41a、dfa791c、052118e、3858958 |
| 2 | 多片合併＋新模式（F）、CLI 機器可讀介面＋health 接線（G）、網頁介面（H） | ea42afa、b31fb04、96e79df |
| 3 | openai-compat 接線修正、README／docstring、打包驗證抓到的動態 import 問題 | f342341、a3095fb、4f307da |

### 驗收對照

- [x] 同一支影片處理一次後，不呼叫 AI 就能輸出 Markdown、樹狀圖（5 種＋網頁版）、3 種 HTML 範本——打包的 exe 用範例分析跑 `--render --outputs all`，10 種全部產生。
- [x] 2 支以上可合併成一份，各支原本的筆記不受影響（test_collection）。
- [x] STT 可切本機／雲端；沒金鑰或雲端失敗時清楚報錯或（設定允許時）退回本機，本機路徑不受影響（test_stt）。
- [x] 舊資料夾（只有 notes、沒有 analysis.json）照常開啟，只要 Markdown 時直接沿用（test_pipeline）。
- [x] 測試全過（295 項）、`git status` 乾淨。
- [~] `build.ps1 video-notes` 的冒煙測試：**改用 `-NoSmoke` 打包 ＋ exe 的 CLI 驗證**（`--check --json`、`--library --json`、`--render`）。
  原因：預設冒煙測試會把 GUI 伺服器開在本機網路埠，擁有者的全域規則是這台電腦不開網路埠。GUI 要擁有者自己開一次確認。

### 沒做或改了做法的地方

- **還沒用真的影片＋真的 AI 跑過**，網頁畫面與範本也還沒在瀏覽器裡看過——寫進 docs/OPEN_ISSUES.md 的 Q6（建議實測後再發 2.2.0）。
- **沒有發版**：版本號仍是 2.1.0（擁有者沒要求發版）。
- `tree-xmind` 沒用真的 XMind 打開過；Mermaid 的跳脫寫法、Gemini 的 mp3 輸入沒實測（docs/tree-formats.md、OPEN_ISSUES）。
- HTML 範本：程式把 analysis 直接填進範本（AI 不另外為範本產生內容），因為 analysis 本身就是 AI 整理好的乾淨資料；這樣換範本完全不花 token。
- 本檔原本寫「主 session 不派 agent 做第 0 波」——照做；第 2 波原計畫的「G 輸出」併進第 1 波的 D（HTML 填範本不需要 AI），第 2 波改成 F 合併、G CLI、H 網頁。
