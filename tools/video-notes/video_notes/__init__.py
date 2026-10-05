"""Video Notes：影片網址 → 下載 → 逐字稿 → AI 整理成 Notion 筆記。

模組分工（每個都可以單獨 import、單獨測）：

    naming      網址 → 平台 / ID / 短影音或一般影片；每支影片的資料夾與檔名
    config      設定與預設值、輸出資料夾的三種選擇
    media       下載（yt-dlp）、抽音訊（ffmpeg）
    transcribe  語音辨識（faster-whisper，自動選 GPU / CPU）、逐字稿格式
    profiles    整理方案（prompts/ 底下的 TOML）：類型、加料、常用組合
    summarize   呼叫 LLM 寫筆記：自動分類、長影片分段、固定的筆記標頭
    pipeline    串起上面全部，決定每個階段沿用還是重做
    jobs        多支影片同時處理（GUI 與 CLI 批次共用）
    notify      socket 模式：把結果 POST 給別的程式
    cli / web   兩種介面，底層完全相同
"""
