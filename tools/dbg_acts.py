import sys, pathlib
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")
from ahlcg.data.pool import CardPool
pool = CardPool.load()
for code in ("01105","01106","01107","01108","01109","01110","01122","01143","01144","01145","01146","01147","01148"):
    d = pool.get(code)
    rec = d.meta.get("arkhamdb") or {}
    print(f"### {code} | {d.name}")
    print("  text      :", repr((d.text or "").strip()[:90]))
    print("  flavor    :", repr((rec.get('flavor') or '').strip()[:90]))
    print("  back_text :", repr((rec.get('back_text') or '').strip()[:90]))
