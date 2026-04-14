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

# Locate workspace root (three levels up from src/core/)
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))   # src/core → src → root
_LANG_DIR  = os.path.join(_ROOT, "language")
_CONFIG_FILE = os.path.join(_ROOT, "language_config.json")
_DEFAULT_LANG = "zh-tw"


class LanguageManager:
    def __init__(self):
        self._strings: dict = {}
        self._current_lang: str = _DEFAULT_LANG
        self._load_config()
        self.load_language(self._current_lang)

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
            with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump({"language": self._current_lang}, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ── Language loading ─────────────────────────────────────────────────
    def load_language(self, lang_code: str) -> bool:
        """Load a language file by code (e.g. 'en', 'zh-tw').
        Returns True on success, False if file not found / unreadable."""
        path = os.path.join(_LANG_DIR, f"{lang_code}.json")
        if not os.path.exists(path):
            # Fallback: try _DEFAULT_LANG, then keep current strings
            if lang_code != _DEFAULT_LANG:
                return self.load_language(_DEFAULT_LANG)
            return False
        try:
            with open(path, "r", encoding="utf-8") as f:
                self._strings = json.load(f)
            self._current_lang = lang_code
            self._save_config()
            return True
        except Exception:
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
            try:
                with open(path, "r", encoding="utf-8") as f:
                    strings = json.load(f)
                text = strings.get(key, default if default is not None else f"[{key}]")
            except Exception:
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
