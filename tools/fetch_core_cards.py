"""Fetch the core-set cards that the bulk ArkhamDB endpoint does not serve.

The bulk endpoint only returns current printings, so every Night of the Zealot
encounter card has to be fetched by code.  Codes are taken from the TTS card
database (reference/carddb.json), which lists the real official numbering.

Run:  python tools/fetch_core_cards.py
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "reference"
BULK = REF / "arkhamdb_cards.json"
CARDDB = REF / "carddb.json"
CACHE = REF / "arkhamdb_fetched.jsonl"
DEST = REF / "arkhamdb_core.json"
CARD_URL = "https://arkhamdb.com/api/public/card/{code}"


def fetch(code: str, attempts: int = 3) -> dict | None:
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(CARD_URL.format(code=code), headers={"User-Agent": "ahlcg-local-project/0.1"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
        except Exception:
            pass
    return None


def main() -> None:
    bulk = json.loads(BULK.read_text(encoding="utf-8"))
    by_code = {c["code"]: c for c in bulk}
    print(f"=== bulk cards: {len(by_code)}")

    carddb = json.loads(CARDDB.read_text(encoding="utf-8"))
    wanted: set[str] = set()
    for cid in carddb:
        base = str(cid).split("-")[0]
        if re.fullmatch(r"01\d{3}[a-z]?", base):
            wanted.add(base)
    wanted.update(by_code)  # keep everything the bulk gave us
    print(f"=== wanted codes (core set family): {len(wanted)}")

    cached: dict[str, dict] = {}
    if CACHE.exists():
        for line in CACHE.read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                cached[record["code"]] = record
        print(f"=== cache hits: {len(cached)}")

    todo = sorted(code for code in wanted if code not in by_code and code not in cached)
    print(f"=== fetching {len(todo)} missing codes with 8 threads")
    fetched: list[dict] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        for record in pool.map(fetch, todo):
            if record is not None:
                fetched.append(record)
    print(f"=== fetched {len(fetched)} / {len(todo)} (missing codes are numbering gaps)")

    with CACHE.open("a", encoding="utf-8") as handle:
        for record in fetched:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            cached[record["code"]] = record

    merged = dict(by_code)
    merged.update(cached)
    DEST.write_text(json.dumps(merged, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    print(f"=== wrote {len(merged)} cards to {DEST}")

    core01 = {c: r for c, r in merged.items() if c.startswith("01")}
    print(f"=== core-set cards (01xxxx): {len(core01)}")
    print("    types:", dict(Counter(r.get("type_code") for r in core01.values())))
    encounters: dict[str, int] = Counter(str(r.get("encounter_code")) for r in core01.values())
    print("    encounter sets:", dict(sorted(encounters.items())))
    print("    packs:", dict(Counter(r.get("pack_code") for r in core01.values())))

    print("\n=== field check for the cards the engine needs ===")
    for code in ("01111", "01105", "01108", "01116", "01093", "01001", "01020", "01166"):
        record = merged.get(code)
        if not record:
            print(f"  [{code}] MISSING")
            continue
        keys = (
            "code", "name", "type_code", "real_slot", "cost", "shroud", "clues", "clues_fixed",
            "doom", "victory", "enemy_fight", "enemy_evade", "enemy_damage", "enemy_horror",
            "health", "sanity", "skill_willpower", "skill_intellect", "skill_combat", "skill_agility",
            "real_text", "traits",
        )
        print(f"  [{code}] " + json.dumps({k: record[k] for k in keys if k in record}, ensure_ascii=False)[:520])


if __name__ == "__main__":
    main()
