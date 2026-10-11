import sys, pathlib
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")
from ahlcg.data.pool import CardPool
pool = CardPool.load()
for code in ("01096","01097","01098","01099","01100","01101","01102","01103"):
    d = pool.get(code)
    print(f"### {code} | {d.name}")
    print((d.text or "").strip())
