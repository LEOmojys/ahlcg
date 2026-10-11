"""Pre-chew the data each scenario task needs, so agents never read the big files.

Reading the 140 KB rules reference or the 2.9 MB ArkhamDB dump kills a subagent's
context budget.  This writes small, task-sized extracts instead.

Run: python tools/make_task_data.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

REF = Path(__file__).resolve().parents[1] / "reference"
core = json.loads((REF / "arkhamdb_core.json").read_text(encoding="utf-8"))

SCENARIOS = {
    "arkham": {
        "name": "第二章：午夜面具 (The Midnight Masks)",
        "reference_card": "01120",
        "encounter_sets": ["arkham", "chilling_cold", "nightgaunts", "cultists", "locked_doors", "pentagram"],
    },
    "tentacles": {
        "name": "第三章：深渊吞噬者 (The Devourer Below)",
        "reference_card": "01142",
        "encounter_sets": [
            "tentacles", "ancient_evils", "striking_fear", "ghouls", "cultists",
            "agents_of_yog", "agents_of_cthulhu", "agents_of_shub", "agents_of_hastur",
        ],
    },
    "torch": {
        "name": "第一章：集结 (The Gathering)",
        "reference_card": "01104",
        "encounter_sets": ["torch", "rats", "ghouls", "striking_fear", "ancient_evils", "chilling_cold"],
    },
}

FIELDS = (
    "code", "name", "type_code", "faction_code", "quantity", "cost", "xp", "real_slot",
    "traits", "real_text", "back_text", "health", "health_per_investigator", "sanity",
    "enemy_fight", "enemy_evade", "enemy_damage", "enemy_horror", "shroud", "clues",
    "clues_fixed", "doom", "victory", "vengeance", "is_unique", "encounter_code", "encounter_name",
)

out: dict[str, dict] = {}
for code, meta in SCENARIOS.items():
    cards: dict[str, dict] = {}
    for set_code in meta["encounter_sets"]:
        for card_code, record in core.items():
            if record.get("encounter_code") != set_code:
                continue
            cards[card_code] = {f: record[f] for f in FIELDS if f in record and record[f] not in (None, "", False)}
    out[code] = {
        "name": meta["name"],
        "reference_card": meta["reference_card"],
        "encounter_sets": meta["encounter_sets"],
        "cards": dict(sorted(cards.items())),
    }
    print(f"{code:10} {len(cards):3d} cards, {meta['name']}")

target = REF / "notz_scenario_data.json"
target.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"\nwrote {target} ({target.stat().st_size/1024:.0f} KB)")

# a short rules digest: only the passages an implementer actually needs
RULES = Path(__file__).resolve().parents[1] / "reference" / "pdf" / "rules_reference_core.txt"
if RULES.exists():
    text = RULES.read_text(encoding="utf-8")
    digest_bits = []
    for marker, span in (
        ("I. Mythos phase", 1500),
        ("II. Investigation phase", 1800),
        ("3.1 Enemy phase begins", 900),
        ("IV. Upkeep phase", 900),
        ("Attack of Opportunity", 900),
        ("\nHunter\n", 700),
        ("\nAloof\n", 500),
        ("\nMassive\n", 500),
        ("\nRetaliate\n", 500),
        ("\nResign\n", 700),
        ("\nParley\n", 500),
        ("Advancing to Next Scenario", 700),
        ("\nTrauma\n", 700),
        ("Experience", 1200),
        ("\nDefeat\n", 1200),
    ):
        idx = text.find(marker)
        if idx >= 0:
            digest_bits.append(f"### {marker.strip()}\n" + " ".join(text[idx : idx + span].split()))
    digest = "# 规则要点摘录（自动生成，来自官方规则参考）\n\n" + "\n\n".join(digest_bits)
    (REF / "rules_digest.md").write_text(digest, encoding="utf-8")
    print(f"wrote {REF / 'rules_digest.md'} ({(REF / 'rules_digest.md').stat().st_size/1024:.0f} KB)")
