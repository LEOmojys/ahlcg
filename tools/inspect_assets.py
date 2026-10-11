"""Inspect the Tabletop Simulator AHLCG asset pack.

Walks the TTS object tree, extracts every named object (cards, decks, bags,
tiles), builds a URL -> local image-file index, and writes a reusable JSON
index to reference/tts_objects.json.

Run:  python tools/inspect_assets.py
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterator

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

ASSETS = Path(r"C:\Users\假烟桑··\Desktop\一步到胃")
PACK = ASSETS / "ahlcg图包一步到胃版"
MOD_JSON = PACK / "Mods" / "Workshop" / "Arkham SCE 3.9.1.json"
IMAGES = PACK / "Mods" / "Images"
OUT = Path(__file__).resolve().parents[1] / "reference"


def image_key(url: str) -> str:
    """TTS stores a downloaded image as the URL with non-alphanumerics stripped."""
    return re.sub(r"[^A-Za-z0-9]", "", url).lower()


def walk(obj: Any) -> Iterator[dict[str, Any]]:
    """Yield every dict in the nested ObjectStates / ContainedObjects tree."""
    if isinstance(obj, dict):
        yield obj
        for child in obj.get("ContainedObjects") or []:
            yield from walk(child)
        for child in obj.get("States") or {}:
            value = (obj.get("States") or {}).get(child)
            yield from walk(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from walk(item)


def face_urls(obj: dict[str, Any]) -> list[str]:
    out = []
    for entry in (obj.get("CustomDeck") or {}).values():
        if isinstance(entry, dict) and entry.get("FaceURL"):
            out.append(entry["FaceURL"])
    if obj.get("FaceURL"):
        out.append(obj["FaceURL"])
    return out


def main() -> None:
    OUT.mkdir(exist_ok=True)
    data = json.loads(MOD_JSON.read_text(encoding="utf-8-sig", errors="replace"))
    top = data.get("ObjectStates") or []
    print(f"=== top level ObjectStates: {len(top)}")
    for obj in top[:40]:
        if not isinstance(obj, dict):
            continue
        contained = len(obj.get("ContainedObjects") or [])
        print(
            f"   {obj.get('Name','?'):<18} nickname={str(obj.get('Nickname'))[:38]!r:<42}"
            f" contained={contained:<5} desc={str(obj.get('Description'))[:40]!r}"
        )

    objects = list(walk(top))
    print(f"\n=== total objects in tree: {len(objects)}")
    named = [o for o in objects if o.get("Nickname")]
    described = [o for o in objects if o.get("Description")]
    gmnote = [o for o in objects if o.get("GMNotes")]
    carded = [o for o in objects if o.get("CardID")]
    print(f"    with Nickname   : {len(named)}")
    print(f"    with Description: {len(described)}")
    print(f"    with GMNotes    : {len(gmnote)}")
    print(f"    with CardID     : {len(carded)}")

    urls: Counter[str] = Counter()
    for obj in objects:
        for url in face_urls(obj):
            urls[url] += 1
    print(f"\n=== distinct FaceURLs: {len(urls)}")

    index = {image_key(p.name.rsplit(".", 1)[0]): p.name for p in IMAGES.glob("*")} if IMAGES.exists() else {}
    # local file names are the stripped URL *plus* the extension
    local = {image_key(p.stem + p.name[-4:]): p.name for p in IMAGES.glob("*")}
    local2 = {image_key(p.name): p.name for p in IMAGES.glob("*")}
    hit1 = sum(1 for u in urls if image_key(u) in local2 or image_key(u) in local)
    print(f"=== local image files: {len(local2)}; FaceURLs matched locally: {hit1}/{len(urls)}")

    print("\n=== sample cards (nickname / description) ===")
    for obj in named[:12]:
        desc = " | ".join(str(obj.get("Description") or "").splitlines())[:150]
        print(f"   {str(obj.get('Nickname'))[:34]:<36} cardid={str(obj.get('CardID')):<8} {desc}")

    print("\n=== sample GMNotes payload ===")
    for obj in gmnote[:3]:
        raw = str(obj.get("GMNotes"))
        print(f"   len={len(raw)}: {raw[:300]!r}")

    entries = []
    for obj in objects:
        if not (obj.get("Nickname") or obj.get("Description")):
            continue
        entries.append(
            {
                "name": obj.get("Name"),
                "nickname": obj.get("Nickname"),
                "description": obj.get("Description"),
                "gm_notes": obj.get("GMNotes"),
                "card_id": obj.get("CardID"),
                "face_urls": face_urls(obj),
                "deck_ids": list((obj.get("CustomDeck") or {}).keys()),
                "tags": obj.get("Tags"),
            }
        )
    (OUT / "tts_objects.json").write_text(json.dumps(entries, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n=== wrote {len(entries)} entries to reference/tts_objects.json")

    deck_names = Counter()
    for obj in objects:
        for entry in (obj.get("CustomDeck") or {}).values():
            if isinstance(entry, dict):
                deck_names[str(entry.get("NumWidth")) + "x" + str(entry.get("NumHeight"))] += 1
    print("=== deck grid shapes (NumWidth x NumHeight):", deck_names.most_common(8))


if __name__ == "__main__":
    main()
