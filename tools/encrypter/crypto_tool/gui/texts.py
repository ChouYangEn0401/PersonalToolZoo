"""新介面上所有給人看的字。改文案只改這裡；規格見 docs/ui-spec.md。"""

APP_NAME = "CryptoTool Pro"
TAGLINE = "把檔案鎖起來，只有你的金鑰或密語打得開"

TAB_ENCRYPT = "加密"
TAB_DECRYPT = "解密"
TAB_KEYS = "金鑰"
TAB_ABOUT = "關於"

THEME_TO_DARK = "深色"
THEME_TO_LIGHT = "淺色"

STATUS_READY = "準備好了"
STATUS_WORKING = {"encrypt": "加密中…", "decrypt": "解密中…"}
STATUS_DONE = {"encrypt": "加密完成", "decrypt": "解密完成"}
STATUS_FAILED = {"encrypt": "加密沒有完成", "decrypt": "解密沒有完成"}

STEP_INPUT = {"encrypt": "① 要加密什麼", "decrypt": "① 要解開哪個檔案"}
DROP_HINT = {
    "encrypt": "把檔案或資料夾拖到這裡",
    "decrypt": "把 .isd2 加密檔拖到這裡",
}
PICK_FILE = "選檔案…"
PICK_FOLDER = "選資料夾…"
NOTHING_CHOSEN = "還沒選"

STEP_KEY = {"encrypt": "② 用什麼鎖", "decrypt": "② 用什麼開"}
KEY_MODE_PASSPHRASE = "密語（自己記的一句話）"
KEY_MODE_KEYFILE = "金鑰檔"
PASSPHRASE_LABEL = "密語"
PASSPHRASE_CONFIRM_LABEL = "再輸入一次"
SHOW_PASSPHRASE = "顯示"
KEYFILE_LABEL = "金鑰檔"
BROWSE = "瀏覽…"
KEYFILE_HINT = "還沒有金鑰檔？到「金鑰」分頁產生一把。"

STEP_OUTPUT = "③ 存到哪裡"
SAVE_AS = "另存…"

ADVANCED_SHOW = "▸ 進階設定"
ADVANCED_HIDE = "▾ 進階設定"
CIPHER_LABEL = "加密法"
CIPHER_CHOICES = [
    ("aes-256-gcm", "AES-256-GCM（預設）"),
    ("chacha20-poly1305", "ChaCha20-Poly1305"),
]
CIPHER_NOTE = "兩種都是標準的認證加密，安全性相當；不確定就用預設。"
OVERWRITE = "輸出檔已存在時直接覆蓋"
KEEP_TAR = "內容是資料夾時不解開，存成 .tar 檔"

GO = {"encrypt": "加密", "decrypt": "解密"}

STRENGTH_LABELS = ["", "太短，容易被猜到", "還可以，再長一點更好", "不錯"]

PROBLEMS_TITLE = "還差一點"
PROBLEM_NO_INPUT = {"encrypt": "還沒選要加密的檔案或資料夾。", "decrypt": "還沒選要解密的檔案。"}
PROBLEM_INPUT_GONE = "找不到選的那個檔案或資料夾，可能被移走了。"
PROBLEM_NO_OUTPUT = "還沒決定要存到哪裡。"
PROBLEM_NO_PASSPHRASE = "還沒輸入密語。"
PROBLEM_MISMATCH = "兩次輸入的密語不一樣。"
PROBLEM_NO_KEYFILE = "還沒選金鑰檔。"

SUCCESS_TITLE = {"encrypt": "加密完成", "decrypt": "解密完成"}
SUCCESS_SAVED = "存在：{path}"
SUCCESS_FILES = "共 {n} 個檔案"
SUCCESS_SKIPPED = "注意：略過了 {n} 個連結或特殊檔案，它們沒有被加密。"
SUCCESS_ORIGINAL_KEPT = "原本的檔案沒有被動到；確定加密檔打得開之後，再自己決定要不要刪掉原檔。"
SUCCESS_BACKUP = "金鑰或密語不見就打不開。請在這台電腦以外的地方另外留一份。"

# SealError.code -> (標題, 補充說明)。原因與「怎麼辦」直接用錯誤本身帶的句子。
ERROR_TITLES = {
    "wrong_key": "金鑰或密語不對",
    "corrupt": "這個加密檔壞了或被改過",
    "output_exists": "那個位置已經有東西了",
    "input_missing": "找不到檔案",
    "key_missing": "找不到金鑰",
    "bad_key_format": "金鑰的種類或格式不對",
    "unsupported_format": "這不是這個工具的加密檔",
    "legacy_format": "這是舊版格式（.isd）",
    "unsafe_archive": "這個加密檔的內容不安全，已停止",
    "dependency_missing": "程式的環境沒有裝好",
    "io_error": "讀寫檔案失敗",
    "bad_input": "這樣沒辦法做",
    "internal_bug": "程式出了沒預期到的錯",
}
ERROR_NOTHING_WRITTEN = "沒有產生任何輸出檔。"
LEGACY_OPEN_BUTTON = "開啟舊版工具…"

SEALED_DESCRIPTION = "{cipher}・用{key}加密・內容是{payload}"
SEALED_KEY = {"scrypt": "密語", "raw-key": "金鑰檔"}
SEALED_PAYLOAD = {"file": "一個檔案", "folder": "一個資料夾"}
SEALED_LEGACY = "舊版 .isd 格式：要用「關於」分頁裡的舊版工具才能解。"
KIND_FILE = "檔案"
KIND_FOLDER = "資料夾"

KEYS_INTRO = (
    "金鑰檔是一把隨機產生、很長的鑰匙，比密語安全，也方便讓別的程式自動加解密。"
    "缺點是檔案不見就完全打不開，所以一定要另外備份。"
)
KEYS_NEW_TITLE = "產生新的金鑰檔"
KEYS_NEW_PATH = "存成"
KEYS_NEW_BUTTON = "產生金鑰檔"
KEYS_DEFAULT_NAME = ".decryption_code.env"
KEYS_CREATED = "已產生金鑰檔：{path}"
KEYS_FINGERPRINT = "金鑰指紋：{key_id}（核對備份是不是同一把時用；指紋不是祕密）"
KEYS_BACKUP_WARNING = (
    "現在就把這個檔案複製一份到這台電腦以外的地方（隨身碟、另一台電腦，或印成紙本鎖起來）。"
    "只放在這台電腦，硬碟壞了或重灌，用它加密的東西就永遠打不開。"
    "也不要把金鑰檔跟加密檔放在同一個資料夾或同一個雲端。"
)
KEYS_CHECK_TITLE = "檢查一個金鑰檔"
KEYS_CHECK_BUTTON = "檢查"
KEYS_CHECK_RAW = "可以用：這是一把 32 bytes 的金鑰。指紋：{key_id}"
KEYS_CHECK_PASSPHRASE = "可以用：檔案裡放的是密語（不是隨機金鑰），會當成密語使用。"

ABOUT_LINES = [
    "加密方式：AES-256-GCM 或 ChaCha20-Poly1305（標準的認證加密），密語用 scrypt 轉成金鑰。",
    "加密檔的副檔名是 .isd2。檔案被改過、被截斷或金鑰不對，解密都會明確失敗，不會吐出錯的內容。",
    "資料夾會先打包再加密，解密時還原成資料夾。",
    "別的程式可以用命令列呼叫：python -m crypto_tool encrypt|decrypt|info|keygen（詳見 README）。",
]
ABOUT_LEGACY_TITLE = "舊版工具（實驗性）"
ABOUT_LEGACY_TEXT = (
    "以前的 .isd 格式、Mixture（All-In-One／Layered）、PGP、大檔案分段都收在這裡，"
    "保留是為了解開舊檔。不建議再用它加密新的東西。開啟時畫面會切成深色。"
)
LEGACY_UNAVAILABLE = "舊版工具打不開：缺少舊格式需要的套件（pycryptodome）。請用 run.bat 重新準備環境。"
