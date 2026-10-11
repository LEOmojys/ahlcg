import sys, pathlib
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")
from ahlcg.core.enums import CardType
from ahlcg.data.deck import CORE_PACKS
from ahlcg.data.pool import CardPool
pool = CardPool.load()
by_title = {}
for d in pool.all():
    rec = d.meta.get("arkhamdb") or {}
    if rec.get("pack_code") not in CORE_PACKS or rec.get("encounter_code"):
        continue
    if d.card_type not in (CardType.ASSET, CardType.EVENT, CardType.SKILL, CardType.INVESTIGATOR):
        continue
    by_title.setdefault(d.name, d)
out = []
for d in sorted(by_title.values(), key=lambda x: x.code):
    out.append(f"### {d.code} | {d.name} | {d.card_type.value} | L{d.level}")
    out.append((d.text or "").strip())
SCEN = ["01105","01106","01107","01108","01109","01110","01111","01112","01113","01114","01115","01116","01117","01122","01123","01124","01125","01126","01127","01128","01129","01130","01131","01132","01133","01134","01137","01138","01139","01140","01141","01143","01144","01145","01146","01147","01148","01149","01150","01151","01152","01153","01154","01155","01156","01157"]
out.append("")
out.append("===== SCENARIO =====")
for code in SCEN:
    d = pool.get(code)
    out.append(f"### {code} | {d.name} | {d.card_type.value}")
    out.append((d.text or "").strip())
path = pathlib.Path("reference/zh_worklist.txt")
path.write_text("\n".join(out), encoding="utf-8")
print("entries:", len(by_title), "scenario:", len(SCEN), "bytes:", path.stat().st_size)
