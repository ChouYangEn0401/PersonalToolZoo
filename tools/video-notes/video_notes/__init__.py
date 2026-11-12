"""Video Notes：影片網址 → 下載 → 逐字稿 → AI 分析成 analysis.json → 筆記／樹狀圖／網頁…（可多片合併）。

模組分工（每個都可以單獨 import、單獨測）：

    naming      網址 → 平台 / ID / 短影音或一般影片；每支影片（與合併）的資料夾與檔名
    config      設定與預設值、輸出資料夾的三種選擇
    errors      錯誤合約：ToolError（code／reason／remedy）、退出碼、去敏感資訊
    analysis    analysis.json 的 schema、驗證、讀寫（v2 的核心資產）
    adapters/   可換的四層：source（下載）、stt（語音辨識）、llm（分析用 AI）、render（輸出格式）
    media       yt-dlp 下載、ffmpeg 抽音訊，錯誤轉成錯誤合約
    transcribe  本機語音辨識（faster-whisper，自動選 GPU / CPU）、逐字稿格式
    profiles    整理方案（prompts/ 底下的 TOML）：類型、加料、常用組合、合併方式
    analyze     呼叫 AI 產生 analysis：自動分類、長影片分段、驗證→修復一次→降級
    summarize   舊的 Markdown 寫法（降級用）與共用的影片資訊、分段工具
    collection  多片合併：好幾份 analysis → 一份
    pipeline    串起上面全部，決定每個階段沿用還是重做；reanalyze、render
    library     筆記庫（影片與合併）
    health      依賴壞掉的記帳（連續失敗 3 次就不再自動重試）
    doctor      不連網的自我檢查
    deps        缺 ffmpeg／Deno 時從官方一鍵下載到 data/bin/（核對 SHA-256），並加進 PATH
    jobs        多支影片同時處理（GUI 與 CLI 批次共用）
    notify      socket 模式：把結果 POST 給別的程式
    cli / web   兩種介面，底層完全相同
"""
