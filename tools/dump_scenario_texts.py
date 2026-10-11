import json, sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
core = json.loads(Path("reference/arkhamdb_core.json").read_text(encoding="utf-8"))
sets = {}
for code, r in sorted(core.items()):
    if not code.startswith("01"):
        continue
    sets.setdefault(str(r.get("encounter_code")), []).append(r)

print("=== encounter_code -> encounter_name, count ===")
for key, records in sorted(sets.items()):
    name = next((r.get("encounter_name") for r in records if r.get("encounter_name")), "")
    print(f"  {key:>16}  {len(records):3d}  {name}")

def dump(key):
    print(f"\n{'='*100}\n=== {key} ===")
    for r in sorted(sets.get(key, []), key=lambda x: str(x.get("code"))):
        text = (r.get("real_text") or "").replace("\n", " | ")
        back = (r.get("back_text") or "").replace("\n", " | ")
        print(f"[{r['code']}] {r.get('type_code')} | {r.get('name')} | shroud={r.get('shroud')} clues={r.get('clues')} clues_fixed={r.get('clues_fixed')} doom={r.get('doom')} victory={r.get('victory')}")
        if text:
            print(f"    {text[:500]}")
        if back:
            print(f"    BACK: {back[:400]}")

for key in ("torch", "rats", "ghouls", "striking_fear", "ancient_evils", "chilling_cold"):
    dump(key)
