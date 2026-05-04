"""
LanguageManager — Multi-language support for Git Helper Pro
============================================================
Usage:
    from src.core.language_manager import lm
    lm.t("toolbar.new_project")
    lm.t("msg.switched_to", target="main")   # fills {target}
    lm.load_text("key", lang_code="en")       # explicit language override

Language storage: primary source is language/translations.csv
  Columns: key, zh-tw, zh-cn, en, ... (one column per language code)
  Fallback: individual <lang>.json files (legacy support)
  Newline encoding in CSV: literal \\n sequences are decoded to actual newlines
"""

import csv
import json
import os
import sys
import logging
from typing import Optional

# Resolve runtime root and handle PyInstaller bundles.
# When frozen by PyInstaller, data files bundled via --add-data
# are extracted into sys._MEIPASS. Also avoid writing back
# into the frozen bundle; use a user-writable config location.
_HERE = os.path.dirname(os.path.abspath(__file__))
if getattr(sys, 'frozen', False):
    # When frozen prefer external resources placed next to the exe:
    #  - language_config.json beside the exe
    #  - .lang/GitHelperPro/ as the language folder (preferred)
    #  - fallback to language/ inside the extracted bundle (sys._MEIPASS)
    exe_dir = os.path.dirname(sys.executable)
    candidate_config = os.path.join(exe_dir, "language_config.json")
    candidate_lang_dot = os.path.join(exe_dir, ".lang", "GitHelperPro")
    candidate_lang_plain = os.path.join(exe_dir, "language")
    bundle_root = getattr(sys, '_MEIPASS', _HERE)
    bundle_lang = os.path.join(bundle_root, "language")
    # choose config file location: prefer exe-side config (read/write), else user home
    if os.path.exists(candidate_config) or os.access(exe_dir, os.W_OK):
        _CONFIG_FILE = candidate_config
    else:
        _CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".githelper_config.json")

    # separate bundled vs external language dirs. External (.lang/GitHelperPro or language)
    # will be used as overlays on top of bundled/base languages.
    _BUNDLED_LANG_DIR = bundle_lang if os.path.isdir(bundle_lang) else None
    _EXTERNAL_LANG_DIR = None
    if os.path.isdir(candidate_lang_dot):
        _EXTERNAL_LANG_DIR = candidate_lang_dot
    elif os.path.isdir(candidate_lang_plain):
        _EXTERNAL_LANG_DIR = candidate_lang_plain

    # fall back _LANG_DIR for compatibility
    _LANG_DIR = _EXTERNAL_LANG_DIR or _BUNDLED_LANG_DIR or candidate_lang_dot
    _ROOT = exe_dir
else:
    _ROOT = os.path.dirname(os.path.dirname(_HERE))   # src/core → src → root
    _CONFIG_FILE = os.path.join(_ROOT, "language_config.json")
    _BUNDLED_LANG_DIR = os.path.join(_ROOT, "language")
    _EXTERNAL_LANG_DIR = None
    _LANG_DIR = _BUNDLED_LANG_DIR
_DEFAULT_LANG = "zh-tw"


class LanguageManager:
    def __init__(self):
        # logger: console + file when frozen
        self._setup_logger()

        self._strings: dict = {}
        self._current_lang: str = _DEFAULT_LANG
        self._last_loaded: Optional[str] = None
        self._load_config()
        self.load_language(self._current_lang)

    def _setup_logger(self):
        name = "githelper.language"
        self._logger = logging.getLogger(name)
        if not self._logger.handlers:
            self._logger.setLevel(logging.INFO)
            sh = logging.StreamHandler()
            sh.setFormatter(logging.Formatter("[lang] %(message)s"))
            self._logger.addHandler(sh)
            # if frozen, also add file handler next to exe
            if getattr(sys, 'frozen', False):
                try:
                    exe_dir = os.path.dirname(sys.executable)
                    logpath = os.path.join(exe_dir, "githelper_language.log")
                    fh = logging.FileHandler(logpath, encoding="utf-8")
                    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [lang] %(message)s"))
                    self._logger.addHandler(fh)
                except Exception:
                    pass

    # ── Config persistence ───────────────────────────────────────────────
    def _load_config(self):
        if os.path.exists(_CONFIG_FILE):
            try:
                with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._current_lang = data.get("language", _DEFAULT_LANG)
            except Exception:
                pass

    def _save_config(self):
        try:
            # ensure parent dir exists for exe-side config
            cfg_dir = os.path.dirname(_CONFIG_FILE)
            if cfg_dir and not os.path.isdir(cfg_dir):
                try:
                    os.makedirs(cfg_dir, exist_ok=True)
                except Exception:
                    pass
            with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump({"language": self._current_lang}, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ── CSV helpers ─────────────────────────────────────────────────────
    def _csv_path(self, lang_dir: Optional[str]) -> Optional[str]:
        """Return path to translations.csv under *lang_dir*, or None."""
        if lang_dir and os.path.isdir(lang_dir):
            p = os.path.join(lang_dir, "translations.csv")
            if os.path.exists(p):
                return p
        return None

    def _load_from_csv(self, lang_code: str) -> Optional[dict]:
        """Load a language column from translations.csv.
        External dir takes precedence over bundled (same as JSON override behaviour).
        Returns dict {key: value} on success, or None if CSV / column not found."""
        csv_path = self._csv_path(_EXTERNAL_LANG_DIR) or self._csv_path(_BUNDLED_LANG_DIR)
        if csv_path is None:
            return None
        try:
            with open(csv_path, "r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                if lang_code not in (reader.fieldnames or []):
                    self._logger.warning(
                        f"Column '{lang_code}' not found in {csv_path}. "
                        f"Available: {reader.fieldnames}"
                    )
                    return None
                result = {}
                for row in reader:
                    key = row.get("key", "").strip()
                    if not key:
                        continue
                    value = row.get(lang_code, "")
                    # Decode literal \n sequences → actual newlines
                    result[key] = value.replace("\\n", "\n")
            self._logger.info(f"Loaded '{lang_code}' from CSV: {csv_path}")
            self._last_loaded = csv_path
            return result
        except Exception:
            self._logger.exception(f"Failed to read CSV: {csv_path}")
            return None

    def _available_from_csv(self) -> Optional[dict]:
        """Return {lang_code: display_name} from CSV header columns.
        External dir takes precedence over bundled.
        Returns None when no CSV file is found."""
        csv_path = self._csv_path(_EXTERNAL_LANG_DIR) or self._csv_path(_BUNDLED_LANG_DIR)
        if csv_path is None:
            return None
        try:
            with open(csv_path, "r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                fieldnames = list(reader.fieldnames or [])
                # Language codes are all columns except 'key'
                lang_codes = [c for c in fieldnames if c != "key"]
                # Read display names from _meta.display_name row
                display_map: dict = {}
                for row in reader:
                    if row.get("key", "").strip() == "_meta.display_name":
                        for code in lang_codes:
                            v = row.get(code, "").strip()
                            display_map[code] = v if v else code
                        break
            # Fill missing display names with the code itself
            result = {code: display_map.get(code, code) for code in lang_codes}
            return result
        except Exception:
            self._logger.exception(f"Failed to read CSV headers: {csv_path}")
            return None

    # ── Language loading ─────────────────────────────────────────────────
    def load_language(self, lang_code: str) -> bool:
        """Load a language by code (e.g. 'en', 'zh-tw').
        Tries translations.csv first; falls back to <lang>.json files.
        Returns True on success, False if neither source is found."""
        # 1) Try CSV (preferred)
        csv_data = self._load_from_csv(lang_code)
        if csv_data is not None:
            self._strings = csv_data
            self._current_lang = lang_code
            self._save_config()
            return True

        # 2) Fallback: individual JSON files (bundled base + external overrides)
        base = {}
        if _BUNDLED_LANG_DIR and os.path.isdir(_BUNDLED_LANG_DIR):
            bpath = os.path.join(_BUNDLED_LANG_DIR, f"{lang_code}.json")
            if os.path.exists(bpath):
                try:
                    with open(bpath, "r", encoding="utf-8") as f:
                        base = json.load(f)
                    self._logger.info(f"Loaded bundled language '{lang_code}' from: {bpath}")
                    self._last_loaded = bpath
                except Exception:
                    self._logger.exception(f"Failed to read bundled language file: {bpath}")

        overrides = {}
        if _EXTERNAL_LANG_DIR and os.path.isdir(_EXTERNAL_LANG_DIR):
            epath = os.path.join(_EXTERNAL_LANG_DIR, f"{lang_code}.json")
            if os.path.exists(epath):
                try:
                    with open(epath, "r", encoding="utf-8") as f:
                        overrides = json.load(f)
                    self._logger.info(f"Loaded external language overrides for '{lang_code}' from: {epath}")
                    self._last_loaded = epath
                except Exception:
                    self._logger.exception(f"Failed to read external language file: {epath}")

        if not base and not overrides:
            if lang_code != _DEFAULT_LANG:
                return self.load_language(_DEFAULT_LANG)
            return False

        merged: dict = {}
        merged.update(base)
        merged.update(overrides)
        self._strings = merged
        self._current_lang = lang_code
        self._save_config()
        return True

    # ── Translation API ──────────────────────────────────────────────────
    def load_text(self, key: str, lang_code: str = None, default: str = None, **kwargs) -> str:
        """Return translated text for *key*.

        Parameters
        ----------
        key       : dotted translation key, e.g. "toolbar.new_project"
        lang_code : optional explicit language override; None = current language
        default   : fallback text when key is missing; None → "[key]"
        **kwargs  : named placeholders for str.format(), e.g. target="main"
        """
        if lang_code is not None and lang_code != self._current_lang:
            # 1) Try CSV
            temp = self._load_from_csv(lang_code)
            if temp is None:
                # 2) Fallback to JSON files
                temp_base = {}
                if _BUNDLED_LANG_DIR and os.path.isdir(_BUNDLED_LANG_DIR):
                    bpath = os.path.join(_BUNDLED_LANG_DIR, f"{lang_code}.json")
                    if os.path.exists(bpath):
                        try:
                            with open(bpath, "r", encoding="utf-8") as f:
                                temp_base = json.load(f)
                        except Exception:
                            pass
                temp_overrides = {}
                if _EXTERNAL_LANG_DIR and os.path.isdir(_EXTERNAL_LANG_DIR):
                    epath = os.path.join(_EXTERNAL_LANG_DIR, f"{lang_code}.json")
                    if os.path.exists(epath):
                        try:
                            with open(epath, "r", encoding="utf-8") as f:
                                temp_overrides = json.load(f)
                        except Exception:
                            pass
                temp = {}
                temp.update(temp_base)
                temp.update(temp_overrides)
            text = temp.get(key, default if default is not None else f"[{key}]")
        else:
            text = self._strings.get(key, default if default is not None else f"[{key}]")

        if kwargs:
            try:
                text = text.format(**kwargs)
            except (KeyError, ValueError):
                pass
        return text

    # shorthand — preferred in UI code
    def t(self, key: str, default: str = None, **kwargs) -> str:
        return self.load_text(key, default=default, **kwargs)

    # ── Introspection ────────────────────────────────────────────────────
    @property
    def current_language(self) -> str:
        return self._current_lang

    @property
    def last_loaded(self) -> Optional[str]:
        """Path of the last language file that was actually loaded (or None)."""
        return getattr(self, '_last_loaded', None)

    def available_languages(self) -> dict:
        """Return {code: display_name} for all available language codes.

        Checks translations.csv first (preferred). Falls back to scanning
        individual .json files when no CSV is found.
        """
        # 1) Try CSV
        csv_langs = self._available_from_csv()
        if csv_langs is not None:
            return csv_langs

        # 2) Fallback: scan JSON files
        all_codes: set = set()
        if _BUNDLED_LANG_DIR and os.path.isdir(_BUNDLED_LANG_DIR):
            for fname in os.listdir(_BUNDLED_LANG_DIR):
                if fname.endswith(".json") and not fname.startswith("_"):
                    all_codes.add(fname[:-5])
        if _EXTERNAL_LANG_DIR and os.path.isdir(_EXTERNAL_LANG_DIR):
            for fname in os.listdir(_EXTERNAL_LANG_DIR):
                if fname.endswith(".json") and not fname.startswith("_"):
                    all_codes.add(fname[:-5])

        result = {}
        used_display = set()
        for code in sorted(all_codes):
            display = None
            if _EXTERNAL_LANG_DIR:
                ext = os.path.join(_EXTERNAL_LANG_DIR, f"{code}.json")
                if os.path.exists(ext):
                    try:
                        with open(ext, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        display = data.get("_meta.display_name")
                    except Exception:
                        pass
            if display is None and _BUNDLED_LANG_DIR:
                bundle = os.path.join(_BUNDLED_LANG_DIR, f"{code}.json")
                if os.path.exists(bundle):
                    try:
                        with open(bundle, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        display = data.get("_meta.display_name")
                    except Exception:
                        pass
            display = display if display is not None else code
            if display in used_display:
                display = f"{display} ({code})"
            used_display.add(display)
            result[code] = display
        return result
        


# ── Module-level singleton ───────────────────────────────────────────────
lm = LanguageManager()
