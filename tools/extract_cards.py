"""Extract the card database from the TTS save.

Every card in the mod is a TTS object carrying:
  * Nickname    - the card name (Chinese)
  * Description - the card text (Chinese)
  * CardID      - deck_index * 100 + position on the sheet
  * CustomDeck  - sheet image URL plus the sheet grid (NumWidth x NumHeight)

That is enough to rebuild name, text, and the exact crop rectangle of every
card face inside its sheet image.  Output lands in reference/.

Run:  python tools/extract_cards.py
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterator

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

ASSETS = Path(r"C:\Users\假烟桑··\Desktop\一步到胃")
PACK = ASSETS / "ahlcg图包一步到胃版"
MOD_JSON = PACK / "Mods" / "Workshop" / "Arkham SCE 3.9.1.json"
IMAGES = PACK / "Mods" / "Images"
OUT = Path(__file__).resolve().parents[1] / "reference"


def walk(obj: Any, parent: str = "") -> Iterator[tuple[dict[str, Any], str]]:
    if isinstance(obj, dict):
        label = str(obj.get("Nickname") or obj.get("Name") or parent)
        yield obj, parent
        for child in obj.get("ContainedObjects") or []:
            yield from walk(child, label)
        for value in (obj.get("States") or {}).values():
            yield from walk(value, label)
    elif isinstance(obj, list):
        for item in obj:
            yield from walk(item, parent)


def strip_key(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", text).lower()


def build_image_index() -> dict[str, str]:
    index: dict[str, str] = {}
    if not IMAGES.exists():
        return index
    for path in IMAGES.glob("*"):
        index[strip_key(path.name)] = path.name
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
    print(f"=== image index keys: {len(index)}; files: {len(list(IMAGES.glob('*')))}")

    cards: dict[tuple[str, str], dict[str, Any]] = {}
    gm_patterns: Counter[str] = Counter()
    parents: Counter[str] = Counter()
    total = 0

    for obj, parent in walk(data.get("ObjectStates") or []):
        parent = str(obj.get("Nickname") or parent)
        card_id = obj.get("CardID")
        nickname = str(obj.get("Nickname") or "").strip()
        description = str(obj.get("Description") or "").strip()
        if not nickname:
            continue
        total += 1
        gm = str(obj.get("GMNotes") or "")
        if gm:
            gm_patterns[gm[:40]] += 1
        parents[parent] += 1

        deck_meta = None
        for deck_id, entry in (obj.get("CustomDeck") or {}).items():
            if isinstance(entry, dict) and entry.get("FaceURL"):
                deck_meta = {"deck_id": deck_id, **entry}
                break
        key = (nickname, description)
        record = cards.get(key)
        if record is None:
            record = {
                "name": nickname,
                "text": description,
                "gm_notes": gm,
                "card_ids": [],
                "sheet": None,
                "sheet_file": None,
                "sources": set(),
            }
            cards[key] = record
        if card_id is not None:
            record["card_ids"].append(card_id)
        if deck_meta is not None and record["sheet"] is None:
            record["sheet"] = {
                "face_url": deck_meta.get("FaceURL"),
                "back_url": deck_meta.get("BackURL"),
                "num_width": deck_meta.get("NumWidth"),
                "num_height": deck_meta.get("NumHeight"),
                "unique_back": deck_meta.get("UniqueBack"),
                "deck_id": str(deck_meta.get("deck_id")),
            }
            record["sheet_file"] = resolve_image(str(deck_meta.get("FaceURL") or ""), index)
        record["sources"].add(parent)

    print(f"\n=== named objects walked: {total}")
    print(f"=== distinct (name, text) pairs: {len(cards)}")
    with_sheet = sum(1 for r in cards.values() if r["sheet"])
    with_file = sum(1 for r in cards.values() if r["sheet_file"])
    print(f"=== with sheet metadata: {with_sheet}; sheet image found locally: {with_file}")
    print("=== top parent containers:", parents.most_common(12))

    print("\n=== distinct GMNotes values (first 40 chars) ===")
    for pattern, count in gm_patterns.most_common(15):
        print(f"  {count:6d}  {pattern!r}")

    print("\n=== sample cards ===")
    samples = [r for r in cards.values() if len(r["text"]) > 20][:10]
    for r in samples:
        cid = r["card_ids"][:2]
        print(f"  * {r['name'][:30]!r} ids={cid} sheet={bool(r['sheet'])} file={r['sheet_file']}")
        print(f"    text: {' | '.join(r['text'].splitlines())[:170]}")
        if r["gm_notes"]:
            print(f"    gm  : {' | '.join(r['gm_notes'].splitlines())[:120]}")

    payload = []
    for r in cards.values():
        sheet = r["sheet"]
        crops = []
        if sheet and sheet.get("num_width") and sheet.get("num_height"):
            w, h, n = sheet["num_width"], sheet["num_height"], None
            for card_id in sorted(set(r["card_ids"])):
                idx = card_id % 100
                if idx <= 0:
                    continue
                crops.append({"card_id": card_id, "row": (idx - 1) // w, "col": (idx - 1) % w})
        payload.append(
            {
                "name": r["name"],
                "text": r["text"],
                "gm_notes": r["gm_notes"],
                "card_ids": sorted(set(r["card_ids"])),
                "sheet": sheet,
                "sheet_file": r["sheet_file"],
                "crops": crops,
                "sources": sorted(r["sources"])[:4],
            }
        )
    payload.sort(key=lambda e: e["name"])
    (OUT / "cards_raw.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n=== wrote {len(payload)} card records to reference/cards_raw.json")


if __name__ == "__main__":
    main()
