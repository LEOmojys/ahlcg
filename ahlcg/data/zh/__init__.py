"""Chinese card translations (community wording, keyed by card code).

Each entry carries the English title it translates so the loader can verify the
mapping and fall back by title for reprints (core vs revised core).
"""

from __future__ import annotations

import json
from pathlib import Path

_DIR = Path(__file__).resolve().parent
_table: dict[str, dict[str, str]] | None = None
_by_title: dict[str, dict[str, str]] | None = None


def table() -> dict[str, dict[str, str]]:
    global _table, _by_title
    if _table is None:
        merged: dict[str, dict[str, str]] = {}
        for path in sorted(_DIR.glob("*.json")):
            merged.update(json.loads(path.read_text(encoding="utf-8")))
        _table = merged
        _by_title = {entry["en"]: entry for entry in merged.values() if entry.get("en")}
    return _table


def lookup(code: str, english_name: str) -> dict[str, str] | None:
    """Find the translation for a card, falling back to its English title."""
    entry = table().get(code)
    if entry is None:
        entry = _by_title.get(english_name) if _by_title is not None else None
    return entry


def attach(defn) -> None:
    """Fill name_zh / text_zh on a CardDef when a translation is available."""
    entry = lookup(defn.code, defn.name)
    if entry is None:
        return
    if entry.get("name"):
        defn.name_zh = entry["name"]
    if entry.get("text"):
        defn.text_zh = entry["text"]
    if entry.get("flavor"):
        defn.meta["flavor_zh"] = entry["flavor"]
