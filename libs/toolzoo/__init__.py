"""PersonalToolZoo 的共用程式庫。

工具（tools/<name>/）需要共用的東西才放這裡，目前有：

- ``toolzoo.appdirs`` —— 使用者資料夾（設定檔、金鑰）放哪裡
- ``toolzoo.ai``      —— LLM 呼叫層（OpenAI / Gemini / Claude）＋提示詞工具
- ``toolzoo.webapp``  —— 本機 web app 的啟動器（FastAPI + 瀏覽器）

怎麼讓工具用到它：見 libs/README.md。
"""

__version__ = "0.1.0"
