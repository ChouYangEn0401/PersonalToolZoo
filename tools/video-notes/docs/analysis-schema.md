# analysis.json 格式（schema v1）

每支影片（或多片合併）分析一次後存下來的結構化結果。之後要輸出 Markdown、樹狀圖、HTML 範本，
或交給其他工具（PPT、Word 的 skills），都只讀這份，不用再花分析的 token。
程式定義在 [`video_notes/analysis.py`](../video_notes/analysis.py)，**改 schema 時兩邊一起改，並把 `SCHEMA_VERSION` 加一**。

## 放在哪

| 種類 | 位置 |
|---|---|
| 單支影片 | `<影片資料夾>/analysis.<slug>.json`（`slug` 與 `notes.<slug>.md` 相同，例如 `news+timeline`） |
| 多片合併 | `<輸出資料夾>/collections/<YYYYMMDD-HHMMSS> <標題>/analysis.<slug>.json`，旁邊有 `collection.json` |
| 其他輸出 | 同一資料夾的 `outputs/<slug>.<renderer><副檔名>`；Markdown 維持 `notes.<slug>.md` |

舊資料夾（只有 `notes.*.md`、沒有 `analysis.*.json`）照常可以開啟；要產生其他輸出時先「重新分析」（沿用逐字稿，不重新下載）。

## 原則

- **純文字、平坦**：欄位裡不放 Markdown 或 HTML 符號，排版由輸出層決定。
- **AI 只填「AI 欄位」**，其餘由程式填，不讓模型抄錯網址、時間、版本。
- **所有文字都是不可信的外部資料**（來自影片標題、逐字稿）：輸出時一律跳脫；連結只允許 `http`／`https`。
- 時間一律是**秒數**（數字或 `null`）。
- 讀到 `schema_version` 比程式新的檔案 → 明確報錯（`dependency_outdated`），不默默亂讀。

## 欄位

### 程式填的

| 欄位 | 型別 | 說明 |
|---|---|---|
| `schema_version` | int | 目前是 `1` |
| `kind` | `"video"` \| `"collection"` | |
| `title` | str | 影片標題；合併時是使用者給的或 AI 取的標題 |
| `mode` | `{profile, modifiers[], focus}` | 使用者選的模式（`auto` 已解析成實際的 profile） |
| `language` | str | 逐字稿主要語言（`zh`、`en`…）；合併時取多數 |
| `sources` | `[{id, url, title, channel, duration, date, folder}]` | 單支影片 1 筆；合併時每支 1 筆。`id` = `<平台>:<影片 ID>` |
| `members` | `[str]` | 只有合併用：成員 analysis 檔（相對輸出資料夾的路徑） |
| `provenance` | `{source_hash, stt:{adapter, model}, analyzer:{provider, model}, prompt_version, created_at}` | 這份是怎麼做出來的 |
| `cost` | `{input_tokens, output_tokens, estimated, audio_seconds}` | 有實際值就填實際值，否則估計並 `estimated: true` |
| `quality_flags` | `[str]` | 見下表 |

### AI 填的

| 欄位 | 型別 | 說明 |
|---|---|---|
| `summary` | str（必填） | 一句話結論 |
| `overview` | str | 2～4 句概述 |
| `sections` | `[Section]`（必填，至少 1） | 筆記主體，依 profile 的「筆記格式」段落排列；就是樹狀圖的樹 |
| `key_points` | `[str]` | 全片最重要的 3～7 點 |
| `timeline` | `[{time, label, detail}]` | 「時間軸」加料 |
| `terms` | `[{term, definition}]` | 「名詞解釋」加料 |
| `actions` | `[str]` | 「行動清單」加料 |
| `quotes` | `[{text, speaker, time}]` | 「金句」加料 |
| `perspectives` | `[{who, stance}]` | 各方說法（新聞、財經常用） |
| `caveats` | `[str]` | 風險、未證實、影片沒說清楚的地方 |
| `tags` | `[str]` | 3～8 個主題標籤 |
| `layout_hint` | `{template, tree_depth}` | AI 依內容建議的呈現：`template` 是 `sheet`／`longform`／`tabs`；`tree_depth` 1～6 |

`Section` = `{title, summary, points: [str], start: 秒數|null, children: [Section]}`，最多 6 層。
加料（timeline／terms／actions／quotes）的內容只放在對應欄位，不在 `sections` 裡重複。

### quality_flags

| 旗標 | 意思 |
|---|---|
| `schema_repair_failed` | AI 兩次都沒給出合格 JSON；這份是降級結果（只有 summary 與一個段落），輸出層要提醒 |
| `stt_fallback_local` | 雲端語音辨識失敗，退回本機 Whisper |
| `transcript_low_confidence` | 語音辨識品質可疑 |
| `truncated_input` | 輸入被截斷 |
| `estimated_cost` | `cost` 是估計值 |
| `member_missing` | 合併時有成員讀不到，已略過 |

## 範例（單支影片）

```json
{
  "schema_version": 1,
  "kind": "video",
  "title": "台積電漲太多？鴻海卻漲不動",
  "mode": {"profile": "finance", "modifiers": ["timeline"], "focus": ""},
  "language": "zh",
  "summary": "主持人認為台積電短線漲多但基本面仍強，鴻海受 AI 伺服器毛利拖累。",
  "overview": "節目比較兩檔權值股近一季的走勢與法說會重點……",
  "sections": [
    {"title": "台積電", "summary": "", "points": ["先進封裝產能明年再翻倍", "毛利率指引 58%"], "start": 62,
     "children": [{"title": "風險", "summary": "", "points": ["匯率", "地緣政治"], "start": null, "children": []}]},
    {"title": "鴻海", "summary": "", "points": ["AI 伺服器營收占比提高但毛利低"], "start": 410, "children": []}
  ],
  "key_points": ["……"],
  "timeline": [{"time": 62, "label": "台積電法說會重點", "detail": ""}],
  "terms": [], "actions": [], "quotes": [],
  "perspectives": [{"who": "主持人", "stance": "台積電短線過熱"}],
  "caveats": ["節目內容不構成投資建議"],
  "tags": ["台積電", "鴻海", "AI 伺服器"],
  "layout_hint": {"template": "longform", "tree_depth": 3},
  "sources": [{"id": "youtube:knWPw9_a5qY", "url": "https://youtu.be/knWPw9_a5qY", "title": "台積電漲太多？鴻海卻漲不動",
               "channel": "……", "duration": 1520, "date": "2026-10-01", "folder": "台積電漲太多？鴻海卻漲不動 [video-knWPw9_a5qY]"}],
  "members": [],
  "provenance": {"source_hash": "3f1c…", "stt": {"adapter": "local", "model": "medium"},
                 "analyzer": {"provider": "claude-sub", "model": "sonnet"}, "prompt_version": "finance+timeline@1",
                 "created_at": "2026-11-12T20:00:00"},
  "cost": {"input_tokens": 18000, "output_tokens": 2100, "estimated": true, "audio_seconds": 1520},
  "quality_flags": ["estimated_cost"]
}
```

## 錯誤合約（所有 adapter 共用）

失敗一律是 `video_notes.errors.ToolError`，序列化成：

```json
{"code": "dependency_outdated", "reason": "yt-dlp 太舊，跟不上 YouTube 改版", "retryable": false,
 "remedy": {"kind": "needs_update", "action": "…\\python.exe -m pip install -U \"yt-dlp[default]<2028\"", "doc": "tools/video-notes/README.md"},
 "detail": "DownloadError: ... HTTP Error 403 ...", "source": "yt-dlp"}
```

| code | 意思 | CLI 退出碼 |
|---|---|---|
| `bad_input`、`unsupported_source` | 只有這次輸入有問題 | 2 |
| `dependency_outdated`、`dependency_missing`、`upstream_changed`、`auth_required`、`auth_expired`、`config_invalid` | 依賴或環境 | 3 |
| `network_unreachable`、`rate_limited`、`resource_exhausted` | 暫時性，可重試 | 4 |
| `internal_bug`、`cancelled` | 其他 | 1 |

`remedy.kind`：`needs_update`／`needs_config`／`needs_owner`／`auto_fixable`／`none`。`remedy.action` 只寫出來，程式不會自動執行（例如不自動 `pip install`）。
