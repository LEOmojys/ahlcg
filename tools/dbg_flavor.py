import sys, pathlib
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")
from ahlcg.data.pool import CardPool
pool = CardPool.load()
for code in ("01105","01106","01108","01143","01146","01107","01109","01110","01144","01145","01147"):
    d = pool.get(code)
    rec = d.meta.get("arkhamdb") or {}
    print(f"### {code} | {d.name}")
    print("F:", (rec.get('flavor') or '').strip().replace("\n", " / "))
