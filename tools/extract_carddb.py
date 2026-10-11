"""Extract the structured card database hidden in the TTS GMNotes.

Each card object in the mod stores a JSON blob in GMNotes holding the official
card code and its machine readable stats, e.g.

    {"id": "01166", "type": "Treachery", "class": "Mythos", ...}

Merging that with the object's Nickname/Description (Chinese name and text) and
its sheet crop rectangle yields a complete, official-code-keyed card database.

Run:  python tools/extract_carddb.py
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterator

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

ASSETS = Path(r"C:\\Users\\假烟桑··\\Desktop\\一步到胃")
PACK = ASSETS / "ahlcg图包一步到胃版"
MOD_JSON = PACK / "Mods" / "Workshop" / "Arkham SCE 3.9.1.json"
IMAGES = PACK / "Mods" / "Images"
OUT = Path(__file__).resolve().parents[1] / "reference"


def walk(obj: Any) -> Iterator[dict[str, Any]]:
    if isinstance(obj, dict):
        yield obj
        for child in obj.get("ContainedObjects") or []:
            yield from walk(child)
        for value in (obj.get("States") or {}).values():
            yield from walk(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from walk(item)


def strip_key(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", text).lower()


def build_image_index() -> dict[str, str]:
    index: dict[str, str] = {}
    if IMAGES.exists():
        for path in IMAGES.glob("*"):
            index[strip_key(path.stem)] = path.name
            for token in re.findall(r"[0-9A-Fa-f]{20,}", path.name):
                index.setdefault(token.lower(), path.name)
    return index


def resolve_image(url: str, index: dict[str, str]) -> str | None:
    if not url:
        return None
    hit = index.get(strip_key(url))
    if hit:
        return hit
    for token in re.findall(r"[0-9A-Fa-f]{20,}", url):
        hit = index.get(token.lower())
        if hit:
            return hit
    return None


def main() -> None:
    OUT.mkdir(exist_ok=True)
    data = json.loads(MOD_JSON.read_text(encoding="utf-8-sig", errors="replace"))
    index = build_image_index()

    db: dict[str, dict[str, Any]] = {}
    type_counter: Counter[str] = Counter()
    key_counter: Counter[str] = Counter()
    bad_json = 0
    json_notes = 0
    examples: list[dict[str, Any]] = []

    for obj in walk(data.get("ObjectStates") or []):
        raw = obj.get("GMNotes")
        if not raw or not isinstance(raw, str):
            continue
        text = raw.strip()
        if not text.startswith("{"):
            continue
        json_notes += 1
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            bad_json += 1
            continue
        if not isinstance(payload, dict):
            continue
        card_id = payload.get("id")
        if not card_id:
            continue
        key_counter.update(payload.keys())
        ctype = str(payload.get("type", "?"))
        type_counter[ctype] += 1

        record = db.setdefault(str(card_id), {"id": str(card_id), "raw": payload})
        record.update({k: v for k, v in payload.items() if k != "id"})
        record["name_zh"] = str(obj.get("Nickname") or record.get("name_zh") or "").strip()
        description = str(obj.get("Description") or "").strip()
        if description and not record.get("text_zh"):
            record["text_zh"] = description
        deck = None
        for deck_id, entry in (obj.get("CustomDeck") or {}).items():
            if isinstance(entry, dict) and entry.get("FaceURL"):
                deck = {"deck_id": str(deck_id), **entry}
                break
        if deck and "sheet" not in record:
            record["sheet"] = {
                "face_url": deck.get("FaceURL"),
                "back_url": deck.get("BackURL"),
                "num_width": deck.get("NumWidth"),
                "num_height": deck.get("NumHeight"),
                "file": resolve_image(str(deck.get("FaceURL") or ""), index),
            }
            cid = obj.get("CardID")
            w = deck.get("NumWidth")
            if cid and w:
                idx = int(cid) % 100
                if idx > 0:
                    record["crop"] = {"row": (idx - 1) // int(w), "col": (idx - 1) % int(w)}
        if len(examples) < 3 and ctype in ("Asset", "Treachery", "Investigator"):
            examples.append(record)

    print(f"=== GMNotes JSON blobs: {json_notes}; unparseable: {bad_json}")
    print(f"=== unique card ids: {len(db)}")
    print("\n=== type histogram (all blobs) ===")
    for name, count in type_counter.most_common():
        print(f"  {count:6d}  {name}")
    print("\n=== field histogram ===")
    for name, count in key_counter.most_common(30):
        print(f"  {count:6d}  {name}")

    cycles: Counter[str] = Counter()
    for cid in db:
        cycles[cid[:2]] += 1
    print("\n=== ids per cycle prefix ===")
    print("  ", dict(sorted(cycles.items())))

    print("\n=== full sample records ===")
    for example in examples:
        trimmed = {k: v for k, v in example.items() if k != "raw"}
        trimmed["raw"] = example.get("raw")
        print(json.dumps(trimmed, ensure_ascii=False, indent=1)[:1800])
        print("---")

    (OUT / "carddb.json").write_text(json.dumps(db, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    print(f"\n=== wrote {len(db)} cards to reference/carddb.json")


if __name__ == "__main__":
    main()
