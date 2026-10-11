"""Download the public ArkhamDB card database for local use.

ArkhamDB exposes a complete, community-maintained card database with the stats
the TTS save does not carry (enemy fight/evade/health, location shroud, ...).
Saved to reference/arkhamdb_cards.json and summarised by pack / encounter set.

Run:  python tools/fetch_arkhamdb.py
"""

from __future__ import annotations

import json
import sys
import urllib.request
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

OUT = Path(__file__).resolve().parents[1] / "reference"
OUT.mkdir(exist_ok=True)
DEST = OUT / "arkhamdb_cards.json"

VARIANTS = {
    "default": "https://arkhamdb.com/api/public/cards/",
    "locale_zh": "https://arkhamdb.com/api/public/cards/?locale=zh",
    "locale_zh_cn": "https://arkhamdb.com/api/public/cards/?locale=zh_CN",
}


def get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "ahlcg-local-project/0.1"})
    with urllib.request.urlopen(req, timeout=90) as resp:
        return resp.read()


def main() -> None:
    for label, url in VARIANTS.items():
        try:
            raw = get(url)
        except Exception as exc:
            print(f"{label}: FAILED {type(exc).__name__} {exc}")
            continue
        data = json.loads(raw)
        roland = next((c for c in data if c.get("code") == "01001"), None)
        name = roland.get("name") if roland else None
        print(f"{label}: {len(data)} cards, {len(raw)/1e6:.2f} MB, 01001 name = {name!r}")
        if label == "default":
            DEST.write_bytes(raw)
            print(f"  saved -> {DEST}")

    data = json.loads(DEST.read_bytes())
    packs = Counter(c.get("pack_code") for c in data)
    print("\n=== cards per pack (top 30) ===")
    for pack, count in packs.most_common(30):
        print(f"  {pack:>14}  {count}")

    core = [c for c in data if c.get("pack_code") == "core"]
    print(f"\n=== core set cards: {len(core)}")
    encounters = Counter(c.get("encounter_code") for c in core)
    print("=== core encounter sets (encounter_code -> count):")
    for code, count in sorted(encounters.items(), key=lambda kv: str(kv[0])):
        name = next((c.get("encounter_name") for c in core if c.get("encounter_code") == code), "?")
        print(f"  {str(code):>16}  {count:4d}  {name}")

    types = Counter(c.get("type_code") for c in core)
    print("\n=== core set types:", dict(types))
    factions = Counter(c.get("faction_code") for c in core)
    print("=== core set factions:", dict(factions))

    print("\n=== a location and a treachery and an act for schema check ===")
    for code in ("01111", "01166", "01108"):
        card = next((c for c in core if c.get("code") == code), None)
        if card:
            print(json.dumps(card, ensure_ascii=False)[:1200])
            print("---")


if __name__ == "__main__":
    main()
