import json, sys
sys.stdout.reconfigure(encoding="utf-8")
core = json.loads(open("reference/arkhamdb_core.json", encoding="utf-8").read())
sets = {}
for c, r in core.items():
    if c.startswith("01"):
        sets.setdefault(str(r.get("encounter_code")), []).append(r)
for key in ("torch", "rats", "ghouls", "striking_fear", "ancient_evils", "chilling_cold", "cultists",
            "nightgaunts", "locked_doors", "pentagram", "arkham", "tentacles",
            "agents_of_yog", "agents_of_cthulhu", "agents_of_shub", "agents_of_hastur"):
    recs = sets.get(key, [])
    total = sum(int(r.get("quantity") or 1) for r in recs)
    items = ", ".join(f"{r['code']}:{r.get('name')}x{r.get('quantity')}" for r in sorted(recs, key=lambda x: x["code"]))
    print(f"{key:>16} uniq={len(recs):3d} total={total:3d}  {items}")
