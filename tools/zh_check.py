import sys
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")
from ahlcg.data.zh import table, lookup
t = table()
print("entries:", len(t))
print("lookup 01016:", lookup("01016", ".45 Automatic")["name"])
print("lookup 01516 (reprint):", lookup("01516", "Machete")["name"] if lookup("01516", "Machete") else None)
