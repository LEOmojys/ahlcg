import collections, pathlib, sys
sys.stdout.reconfigure(encoding="utf-8")
root = pathlib.Path(".")
groups = collections.defaultdict(lambda: [0, 0])
for p in sorted(root.rglob("*.py")):
    parts = p.parts
    if any(x in parts for x in (".git", "__pycache__", "reference")):
        continue
    key = parts[0] if len(parts) == 1 else ("/".join(parts[:2]) if parts[0] == "ahlcg" else parts[0])
    lines = len(p.read_text(encoding="utf-8", errors="replace").splitlines())
    groups[key][0] += 1
    groups[key][1] += lines
total = [0, 0]
for key in sorted(groups):
    n, l = groups[key]
    total[0] += n
    total[1] += l
    print(f"  {key:24} {n:3d} files {l:6d} lines")
print(f"  {'TOTAL':24} {total[0]:3d} files {total[1]:6d} lines")

ref = pathlib.Path("reference")
print("\n=== reference data (extracted from the asset pack + ArkhamDB) ===")
for p in sorted(ref.rglob("*")):
    if p.is_file():
        print(f"  {p.stat().st_size / 1024:9.0f} KB  {p.relative_to(ref)}")
