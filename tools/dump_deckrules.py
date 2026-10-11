import json, sys, collections
sys.stdout.reconfigure(encoding="utf-8")
core = json.loads(open("reference/arkhamdb_core.json", encoding="utf-8").read())
inv = ["01001","01002","01003","01004","01005"]
for code in inv:
    r = core[code]
    print("=" * 90)
    print(code, r.get("name"), "|", r.get("faction_code"), "| health", r.get("health"), "sanity", r.get("sanity"))
    print("  deck_requirements:", r.get("deck_requirements"))
    print("  deck_options     :", str(r.get("deck_options"))[:900])
    print("  text:", (r.get("real_text") or "")[:200])

print("\n=== level-0 card counts per class (player cards, pack core/rcore) ===")
by = collections.defaultdict(lambda: collections.Counter())
weak = []
for code, r in sorted(core.items()):
    if r.get("type_code") not in ("asset","event","skill"): continue
    if not code.startswith("01"): continue
    fac = r.get("faction_code")
    lvl = r.get("xp") or 0
    if lvl == 0:
        by[fac][code] = 1
    sub = str(r.get("subtype_code") or "") + str(r.get("real_subtype") or "")
    if "weakness" in sub.lower():
        weak.append((code, r.get("name"), fac, lvl))
for fac, codes in sorted(by.items()):
    print(f"  {fac:10} level0={len(codes):3d}  total_cards={sum(codes.values())}")
print("\n=== weaknesses in core (code,name,faction,level) ===")
for w in weak:
    print("  ", w)
print("\n=== neutral level-0 list ===")
print("  ", sorted(by.get("neutral", {}).keys()))
print("\n=== guardian level-0 list ===")
print("  ", sorted(by.get("guardian", {}).keys()))
