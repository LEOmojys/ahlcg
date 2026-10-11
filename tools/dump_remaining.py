import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")
from ahlcg.data.pool import CardPool
pool = CardPool.load()
for code in ("01687", "01684", "01082", "01103"):
    d = pool.get(code)
    print(f"[{code}] {d.name} L{d.level} {d.card_class.value}/{d.card_type.value} slot={d.slots} traits={sorted(d.traits)}")
    print("   ", " | ".join(d.text.splitlines()))
