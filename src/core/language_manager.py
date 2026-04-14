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

    # ── Language loading ─────────────────────────────────────────────────
    def load_language(self, lang_code: str) -> bool:
        """Load a language file by code (e.g. 'en', 'zh-tw').
        Returns True on success, False if file not found / unreadable."""
        # Load bundled base strings first (so defaults always present)
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

        # Then load external overrides if any (external files override bundled keys)
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

        # If neither bundled nor external provided the language, fallback to default
        if not base and not overrides:
            if lang_code != _DEFAULT_LANG:
                return self.load_language(_DEFAULT_LANG)
            return False

        # Merge: base <- overrides (overrides win), preserving missing keys from base
        merged = {}
        if isinstance(base, dict):
            merged.update(base)
        if isinstance(overrides, dict):
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
            # Build temporary merged strings from bundled + external (same logic as load_language)
            temp_base = {}
            if _BUNDLED_LANG_DIR and os.path.isdir(_BUNDLED_LANG_DIR):
                bpath = os.path.join(_BUNDLED_LANG_DIR, f"{lang_code}.json")
                if os.path.exists(bpath):
                    try:
                        with open(bpath, "r", encoding="utf-8") as f:
                            temp_base = json.load(f)
                        self._logger.info(f"Temporarily loaded bundled '{lang_code}' from: {bpath}")
                    except Exception:
                        self._logger.exception(f"Failed to read bundled language file: {bpath}")
            temp_overrides = {}
            if _EXTERNAL_LANG_DIR and os.path.isdir(_EXTERNAL_LANG_DIR):
                epath = os.path.join(_EXTERNAL_LANG_DIR, f"{lang_code}.json")
                if os.path.exists(epath):
                    try:
                        with open(epath, "r", encoding="utf-8") as f:
                            temp_overrides = json.load(f)
                        self._logger.info(f"Temporarily loaded external overrides '{lang_code}' from: {epath}")
                    except Exception:
                        self._logger.exception(f"Failed to read external language file: {epath}")
            temp = {}
            if isinstance(temp_base, dict):
                temp.update(temp_base)
            if isinstance(temp_overrides, dict):
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

        A language is available if it exists in _BUNDLED_LANG_DIR or
        _EXTERNAL_LANG_DIR (or both).  Display name resolution:
          1. External file's _meta.display_name  (if present)
          2. Bundled file's _meta.display_name   (fallback)
          3. Language code string                 (last resort)
        """
        # Collect all codes from both dirs
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
            # Try to get display_name: external first, then bundled, then code
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
            # ensure display_name is unique; if duplicate, append code to disambiguate
            if display in used_display:
                display = f"{display} ({code})"
            used_display.add(display)
            result[code] = display

        return result
        


# ── Module-level singleton ───────────────────────────────────────────────
lm = LanguageManager()
