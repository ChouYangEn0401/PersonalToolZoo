"""Video Downloader：yt-dlp 的本機 GUI（也可以當 CLI 用）。

    presets   畫質 / 格式預設組合
    config    設定與預設值
    options   設定 → yt-dlp 參數（經 yt-dlp 自己的 parse_options 轉換）、錯誤說明
    probe     下載前解析：標題、畫質、播放清單內容
    manager   下載佇列、進度、取消 / 重試
    history   下載紀錄
    cli / web 兩種介面
"""
