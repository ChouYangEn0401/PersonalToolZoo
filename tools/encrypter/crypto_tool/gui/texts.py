"""新介面上所有給人看的字。改文案只改這裡；規格見 docs/ui-spec.md。"""

APP_NAME = "CryptoTool Pro"
TAGLINE = "用公開標準格式把檔案鎖起來：別的電腦用 age 或 PGP 也打得開"

TAB_ENCRYPT = "加密"
TAB_DECRYPT = "解密"
TAB_KEYS = "金鑰"
TAB_ABOUT = "關於"

THEME_TO_DARK = "深色"
THEME_TO_LIGHT = "淺色"

STATUS_READY = "準備好了"
STATUS_WORKING = {"encrypt": "加密中…", "decrypt": "解密中…", "keys": "處理中…"}
STATUS_DONE = {"encrypt": "加密完成", "decrypt": "解密完成", "keys": "完成"}
STATUS_FAILED = {"encrypt": "加密沒有完成", "decrypt": "解密沒有完成", "keys": "沒有完成"}

STEP_INPUT = {"encrypt": "① 要加密什麼", "decrypt": "① 要解開哪個檔案"}
DROP_HINT = {
    "encrypt": "把檔案或資料夾拖到這裡（可以一次好幾個）",
    "decrypt": "把加密檔（.age／.gpg／.asc）拖到這裡",
}
PICK_FILE = "選檔案…"
PICK_FOLDER = "選資料夾…"
ADD_MORE = "再加一個…"
CLEAR = "清除"
NOTHING_CHOSEN = "還沒選"
MANY_INPUTS = "{n} 個項目，會先打包成一個檔再加密"

STEP_MODE = "② 用哪一種格式"
MODE_AGE = "簡單模式（age，建議）"
MODE_PGP = "PGP 模式（OpenPGP，需要電腦上有 gpg）"
MODE_NOTE = {
    "age": "公開的 age 格式：任何裝了 age／rage 的電腦也打得開。密語和金鑰不能放在同一個檔。",
    "pgp": "公開的 OpenPGP 格式：GnuPG、Kleopatra 等都打得開；金鑰和密語可以同時放。",
}
PGP_UNAVAILABLE = "這台電腦找不到 gpg，PGP 模式不能用（簡單模式不受影響）。"

STEP_KEY = {"encrypt": "③ 誰可以打開", "decrypt": "② 用什麼開"}
USE_PASSPHRASE = "密語（自己記的一句話）"
USE_KEYS = "金鑰（公鑰）"
PASSPHRASE_LABEL = "密語"
PASSPHRASE_CONFIRM_LABEL = "再輸入一次"
SHOW_PASSPHRASE = "顯示"
RECIPIENT_ENTRY_LABEL = {"age": "公鑰 age1…", "pgp": "公鑰檔 .asc"}
RECIPIENT_ADD = "加入"
RECIPIENT_ADD_FILE = "加入檔案…"
RECIPIENT_HINT = {
    "age": "貼上對方給你的 age1… 公鑰，或選公鑰清單檔／自己的身分檔。還沒有金鑰？到「金鑰」分頁產生一把。",
    "pgp": "選對方給你的 OpenPGP 公鑰檔（.asc）。還沒有？到「金鑰」分頁產生一組。",
}
RECIPIENTS_NONE = "還沒加入任何公鑰"
RECIPIENTS_LIST = "已加入 {n} 把：{items}"
WITH_MASTER = "也讓萬用鎖打得開"
MASTER_NOT_SET = "（還沒設定萬用鎖：到「金鑰」分頁設定）"
MASTER_IS = "（萬用鎖：{value}）"
MASTER_MANY = "{n} 把（{first} 等）"

KEYFILES_LABEL = "鑰匙檔"
KEYFILES_HINT = "age 身分檔（例如 .decryption_code.env）或 OpenPGP 私鑰（.asc）；可以加好幾個。"
FILE_PASSPHRASE_LABEL = "檔案的密語"
KEY_PASSPHRASE_LABEL = "鑰匙檔的密語"
DECRYPT_PASSPHRASE_HINT = "檔案用密語鎖的才填「檔案的密語」；鑰匙檔有加密語保護才填「鑰匙檔的密語」。"
ALL_LAYERS = "一路解到底（裡面還有加密檔，就用同一組鑰匙繼續解）"

STEP_OUTPUT = {"encrypt": "④ 存到哪裡", "decrypt": "③ 存到哪裡"}
SAVE_AS = "另存…"

ADVANCED_SHOW = "▸ 進階設定"
ADVANCED_HIDE = "▾ 進階設定"
ARMOR = "存成文字形式（可以貼在信件或文字檔裡；檔案會大約三分之一）"
OVERWRITE = "輸出檔已存在時直接覆蓋"
KEEP_TAR = "內容是資料夾時不解開，存成 .tar 檔"

GO = {"encrypt": "加密", "decrypt": "解密"}

STRENGTH_LABELS = ["", "太短，容易被猜到", "還可以，再長一點更好", "不錯"]

PROBLEMS_TITLE = "還差一點"
PROBLEM_NO_INPUT = {"encrypt": "還沒選要加密的檔案或資料夾。", "decrypt": "還沒選要解密的檔案。"}
PROBLEM_INPUT_GONE = "找不到選的那個檔案或資料夾，可能被移走了。"
PROBLEM_NO_OUTPUT = "還沒決定要存到哪裡。"
PROBLEM_NO_PASSPHRASE = "勾了密語，但還沒輸入密語。"
PROBLEM_MISMATCH = "兩次輸入的密語不一樣。"
PROBLEM_NO_LOCK = "還沒決定誰可以打開：勾密語、加入公鑰，或勾萬用鎖。"
PROBLEM_AGE_MIX = ("簡單模式（age 規格）不能同時用密語和金鑰（包括萬用鎖）。"
                   "要「密語＋萬用鎖」請改用 PGP 模式，或全部改用金鑰。")
PROBLEM_NO_DECRYPT_KEY = "還沒給鑰匙：加入鑰匙檔，或輸入檔案的密語。"
PROBLEM_PGP_UNAVAILABLE = PGP_UNAVAILABLE

SUCCESS_TITLE = {"encrypt": "加密完成", "decrypt": "解密完成"}
SUCCESS_SAVED = "存在：{path}"
SUCCESS_FORMAT = "格式：{label}"
SUCCESS_WHO = "可以打開的鑰匙：{who}"
SUCCESS_FILES = "共 {n} 個檔案"
SUCCESS_SKIPPED = "注意：略過了 {n} 個連結或特殊檔案，它們沒有被加密。"
SUCCESS_SHORT = "注意：密語少於 12 個字，容易被猜出來。"
SUCCESS_ORIGINAL_KEPT = "原本的檔案沒有被動到；確定加密檔打得開之後，再自己決定要不要刪掉原檔。"
SUCCESS_BACKUP = "鑰匙或密語不見就打不開。請在這台電腦以外的地方另外留一份。"
SUCCESS_USED_MASTER = "用的是萬用鎖。"
SUCCESS_DEPRECATED = "這是 ISD2 預覽格式（已停用）的舊檔；建議用簡單模式重新加密一次。"
LAYERS_DONE = "一共解開 {n} 層，已經解到底。"
LAYERS_STOPPED_TITLE = "解開了一部分"
LAYERS_STOP = "第 {depth} 層需要別的鑰匙：{path}（{lock}）"
LAYERS_STOP_OTHER = "第 {depth} 層解不開：{path}（{reason}）"
LAYERS_DEPTH = "第 {depth} 層超過上限，沒有再往下解：{path}"
WHO_KEYS = "{n} 把金鑰"
WHO_PASSPHRASE = "密語"
WHO_MASTER = "（含萬用鎖）"

# SealError.code -> 標題。原因與「怎麼辦」直接用錯誤本身帶的句子（跟命令列同一套）。
ERROR_TITLES = {
    "wrong_key": "鑰匙或密語不對",
    "corrupt": "這個加密檔壞了或被改過",
    "output_exists": "那個位置已經有東西了",
    "input_missing": "找不到檔案",
    "key_missing": "找不到鑰匙",
    "bad_key_format": "鑰匙的種類或格式不對",
    "unsupported_format": "這不是這個工具認得的加密檔",
    "legacy_format": "這是舊版格式（.isd）",
    "unsafe_archive": "這個加密檔的內容不安全，已停止",
    "dependency_missing": "程式的環境沒有裝好",
    "io_error": "讀寫檔案失敗",
    "bad_input": "這樣沒辦法做",
    "internal_bug": "程式出了沒預期到的錯",
}
ERROR_NOTHING_WRITTEN = "沒有產生任何輸出檔。"
LEGACY_OPEN_BUTTON = "開啟舊版工具…"

FORMAT_LABELS = {
    "age": "age（簡單模式）",
    "openpgp": "OpenPGP（PGP 模式）",
    "isd2-preview": "ISD2 預覽格式（已停用，只能解密）",
    "isd-legacy": "舊版 .isd",
}
SEALED_AGE = "age・{who}・{size}"
SEALED_PGP = "OpenPGP・{who}・{size}"
SEALED_ISD2 = "ISD2 預覽格式（已停用）・用{key}加密・{size}"
SEALED_KEY = {"scrypt": "密語", "raw-key": "金鑰檔"}
SEALED_LEGACY = "舊版 .isd 格式：要用「關於」分頁裡的舊版工具才能解。"
LOCK_KEYS = "金鑰 {n} 把"
LOCK_PASSPHRASE = "密語"
LOCK_PGP_IDS = "收件人 {ids}"
LOCK_PGP_ALSO_PASS = "也可用密語"
LOCK_UNKNOWN = "（要裝了 gpg 才看得到收件人）"
KIND_FILE = "檔案"
KIND_FOLDER = "資料夾"

KEYS_INTRO = (
    "金鑰分兩半：「公鑰」給別人用來加密給你（可以公開），「私鑰」（身分檔）用來打開（一定要保密、一定要備份）。"
    "私鑰不見，用它鎖的東西就永遠打不開——除非當初也加了萬用鎖。"
)
KEYS_AGE_TITLE = "產生簡單模式的金鑰（age）"
KEYS_AGE_PATH = "身分檔存成"
KEYS_PROTECT = "用密語保護私鑰（建議）"
KEYS_DEFAULT_NAME = ".decryption_code.env"
KEYS_AGE_BUTTON = "產生"
KEYS_AGE_CREATED = "已產生身分檔：{path}"
KEYS_PUBLIC = "公鑰（給別人加密用，可以公開）：{key}"
KEYS_PROTECTED = "私鑰有密語保護：之後解密時要輸入這個密語。"
KEYS_NOT_PROTECTED = "注意：私鑰沒有密語保護，拿到這個檔案的人就能解密。"
KEYS_SET_DEFAULT = "設成這台電腦預設的解密鑰匙（只把路徑寫進 .env）"
KEYS_BACKUP_WARNING = (
    "現在就把這個檔案複製一份到這台電腦以外的地方（隨身碟、另一台電腦，或印成紙本鎖起來）。"
    "只放在這台電腦，硬碟壞了或重灌，用它加密的東西就永遠打不開。"
    "也不要把身分檔跟加密檔放在同一個資料夾或同一個雲端。"
)
KEYS_PGP_TITLE = "產生 PGP 金鑰對（OpenPGP）"
KEYS_PGP_PREFIX = "檔名開頭"
KEYS_PGP_NAME = "名稱"
KEYS_PGP_DEFAULT_PREFIX = "encrypter-pgp"
KEYS_PGP_BUTTON = "產生金鑰對"
KEYS_PGP_CREATED = "已產生：公鑰 {public}，私鑰 {secret}"
KEYS_PGP_FINGERPRINT = "指紋：{fpr}（核對用，不是祕密）"
KEYS_MASTER_TITLE = "萬用鎖"
KEYS_MASTER_INTRO = (
    "萬用鎖＝你自己留的一把備用鑰匙。加密時勾「也讓萬用鎖打得開」，同一個檔案別人用自己的鑰匙開、"
    "你用萬用鎖也能開，檔案只多約 100 bytes。這裡只存公鑰；萬用鎖的私鑰請另外收好。"
)
KEYS_MASTER_MANY_HINT = (
    "可以設好幾把（例如兩台電腦各一把、或主＋備）：簡單模式的公鑰用逗號分開，PGP 模式的公鑰檔路徑用分號分開；"
    "按「從身分檔讀…」「選檔案…」會接在後面。每一把都能單獨打開。"
)
KEYS_MASTER_AGE = "簡單模式的萬用鎖公鑰"
KEYS_MASTER_PGP = "PGP 模式的萬用鎖公鑰檔"
KEYS_MASTER_FROM_FILE = "從身分檔讀…"
KEYS_MASTER_SAVE = "儲存"
KEYS_MASTER_SAVED = "已儲存到：{path}"
KEYS_MASTER_COUNT = "萬用鎖：簡單模式 {age} 把、PGP 模式 {pgp} 把。"
KEYS_MASTER_CLEARED = "已清除萬用鎖設定。"
KEYS_CHECK_TITLE = "檢查一個鑰匙檔"
KEYS_CHECK_BUTTON = "檢查"
KEYS_CHECK_AGE = "可以用：age 身分檔，有 {n} 把私鑰。公鑰：{keys}"
KEYS_CHECK_AGE_LOCKED = "可以用：age 身分檔，有密語保護（輸入密語才看得到公鑰）。"
KEYS_CHECK_RECIPIENTS = "這是公鑰清單（給別人加密用）：{keys}"
KEYS_CHECK_PGP_SECRET = "OpenPGP 私鑰檔：用來解密，要保密。"
KEYS_CHECK_PGP_PUBLIC = "OpenPGP 公鑰檔：給別人加密用，可以公開。"
KEYS_CHECK_ISD2 = "ISD2 預覽格式（已停用）的金鑰檔：只能用來解開舊的 .isd2 檔。指紋：{key_id}"
KEYS_CHECK_UNKNOWN = "看不出是哪一種鑰匙檔。"

ABOUT_LINES = [
    "兩種模式都是公開標準格式：簡單模式＝age v1（預設），PGP 模式＝OpenPGP（呼叫電腦上的 gpg）。"
    "這個工具不見了，別的電腦用 age／rage 或 GnuPG 也打得開。",
    "age 的部分是照公開規格自己寫的，通過官方 C2SP 測試向量，但還沒有經過外部審閱；"
    "也還沒有拿真的 age／rage 程式交叉測試過。",
    "萬用鎖＝同一個檔案多加一把鎖：別人用自己的鑰匙開，你用萬用鎖也能開；檔案不會變兩倍大。",
    "檔案被改過、被截斷或鑰匙不對，解密都會明確失敗，不會吐出錯的內容，也不會留下半個檔案。",
    "資料夾或好幾個檔案會先打包成 tar 再加密，解密時還原成資料夾。",
    "別的程式可以用命令列呼叫：python -m crypto_tool encrypt|decrypt|inspect|keygen|rewrap|rekey（詳見 README）。",
    "這一版只加密、不簽章：加密讓別人看不到內容，但不能證明是誰做的。",
]
ABOUT_LEGACY_TITLE = "舊版工具（實驗性）"
ABOUT_LEGACY_TEXT = (
    "以前的 .isd 格式、Mixture（All-In-One／Layered）、舊的 PGP 實驗、大檔案分段都收在這裡，"
    "保留是為了解開舊檔。不建議再用它加密新的東西。開啟時畫面會切成深色。"
)
LEGACY_UNAVAILABLE = "舊版工具打不開：缺少舊格式需要的套件（pycryptodome）。請用 run.bat 重新準備環境。"
