import sys, pathlib
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")
from ahlcg.data.pool import CardPool
pool = CardPool.load()
print("bat attack meta:", pool.get("01074").meta.get("attack"))
from ahlcg.engine.chaos import AUTOFAIL
print("autofail token:", AUTOFAIL, "| type:", getattr(AUTOFAIL, "type", None))
print("priest fight:", pool.get("01116").fight)
from ahlcg.data.deck import CORE_INVESTIGATORS, build_starter_deck
d = build_starter_deck(pool, "01001")
print("roland combat:", pool.get("01001").combat)
