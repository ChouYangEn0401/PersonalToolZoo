"""
LanguageManager — Multi-language support for Git Helper Pro
============================================================
Usage:
    from src.core.language_manager import lm
    lm.t("toolbar.new_project")
    lm.t("msg.switched_to", target="main")   # fills {target}
    lm.load_text("key", lang_code="en")       # explicit language override
"""

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

    # choose language dir preference
    if os.path.isdir(candidate_lang_dot):
        _LANG_DIR = candidate_lang_dot
    elif os.path.isdir(candidate_lang_plain):
        _LANG_DIR = candidate_lang_plain
    elif os.path.isdir(bundle_lang):
        _LANG_DIR = bundle_lang
    else:
        _LANG_DIR = candidate_lang_dot  # default location next to exe (may not exist yet)
    _ROOT = exe_dir
else:
    _ROOT = os.path.dirname(os.path.dirname(_HERE))   # src/core → src → root
    _CONFIG_FILE = os.path.join(_ROOT, "language_config.json")
    _LANG_DIR = os.path.join(_ROOT, "language")
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

    # ── Language loading ─────────────────────────────────────────────────
    def load_language(self, lang_code: str) -> bool:
        """Load a language file by code (e.g. 'en', 'zh-tw').
        Returns True on success, False if file not found / unreadable."""
        path = os.path.join(_LANG_DIR, f"{lang_code}.json")
        self._logger.info(f"Attempting to load language '{lang_code}' from: {path}")
        if not os.path.exists(path):
            self._logger.info(f"Language file not found at: {path}")
            # Fallback: try default language
            if lang_code != _DEFAULT_LANG:
                return self.load_language(_DEFAULT_LANG)
            return False
        try:
            with open(path, "r", encoding="utf-8") as f:
                self._strings = json.load(f)
            self._current_lang = lang_code
            self._last_loaded = path
            self._logger.info(f"Loaded language '{lang_code}' from: {path}")
            self._save_config()
            return True
        except Exception:
            self._logger.exception(f"Failed to load language file: {path}")
            return False

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
            # Load temporarily from the requested language without switching
            path = os.path.join(_LANG_DIR, f"{lang_code}.json")
            self._logger.info(f"Temporarily loading language '{lang_code}' from: {path}")
            try:
                with open(path, "r", encoding="utf-8") as f:
                    strings = json.load(f)
                text = strings.get(key, default if default is not None else f"[{key}]")
                # note: temporary load does not switch current_language, but note source
                self._last_loaded = path
                self._logger.info(f"Temporarily loaded '{lang_code}' from: {path}")
            except Exception:
                self._logger.exception(f"Failed to temporarily load language file: {path}")
                text = default if default is not None else f"[{key}]"
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
        """Return {code: display_name} for every .json file in language/."""
        result = {}
        if not os.path.isdir(_LANG_DIR):
            return result
        for fname in sorted(os.listdir(_LANG_DIR)):
            if fname.endswith(".json") and not fname.startswith("_"):
                code = fname[:-5]
                path = os.path.join(_LANG_DIR, fname)
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    result[code] = data.get("_meta.display_name", code)
                except Exception:
                    result[code] = code
        return result


# ── Module-level singleton ───────────────────────────────────────────────
lm = LanguageManager()
