"""
Locale loading and translation helper.
See architecture/SOP-007-i18n.md.
"""
import json
from pathlib import Path

_locales: dict[str, dict] = {}


def load_locales() -> None:
    for lang in ("de", "en"):
        path = Path(f"locales/{lang}.json")
        _locales[lang] = json.loads(path.read_text(encoding="utf-8"))


def t(key: str, lang: str = "de", **kwargs) -> str:
    """Resolve a dot-separated key. Falls back to 'de', then returns the key itself."""
    parts = key.split(".")
    for locale in (lang, "de"):
        node = _locales.get(locale, {})
        for part in parts:
            node = node.get(part) if isinstance(node, dict) else None
            if node is None:
                break
        if isinstance(node, str):
            return node.format(**kwargs) if kwargs else node
    return key
