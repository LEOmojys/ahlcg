"""Retry the ArkhamDB codes that the parallel fetch lost to rate limiting."""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

REF = Path(__file__).resolve().parents[1] / "reference"
CACHE = REF / "arkhamdb_fetched.jsonl"
DEST = REF / "arkhamdb_core.json"
CARD_URL = "https://arkhamdb.com/api/public/card/{code}"


def fetch(code: str, attempts: int = 4) -> dict | None:
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(CARD_URL.format(code=code), headers={"User-Agent": "ahlcg-local-project/0.1"})
            with urllib.request.urlopen(req, timeout=25) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            time.sleep(0.6 * (attempt + 1))
        except Exception:
            time.sleep(0.6 * (attempt + 1))
    return None


def main() -> None:
    merged = json.loads(DEST.read_text(encoding="utf-8"))
    cached: dict[str, dict] = {}
    if CACHE.exists():
        for line in CACHE.read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                cached[record["code"]] = record

    targets = [f"{n:05d}" for n in range(1094, 1200)]
    todo = [code for code in targets if code not in merged and code not in cached]
    print(f"=== retrying {len(todo)} codes in 01094-01199 with 3 threads")

    fetched: list[dict] = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        for record in pool.map(fetch, todo):
            if record is not None:
                fetched.append(record)
    print(f"=== recovered {len(fetched)} / {len(todo)}")
    if fetched:
        with CACHE.open("a", encoding="utf-8") as handle:
            for record in fetched:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                cached[record["code"]] = record

    merged.update(cached)
    DEST.write_text(json.dumps(merged, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")

    core = {c: r for c, r in merged.items() if c.startswith("01")}
    print(f"=== core-set cards now: {len(core)}")
    from collections import Counter
    print("    encounter sets:", dict(sorted(Counter(str(r.get("encounter_code")) for r in core.values()).items())))

    still = [code for code in targets if code not in merged]
    print(f"=== still absent in 01094-01199 ({len(still)}):", " ".join(still))

    print("\n=== Night of the Zealot card inventory ===")
    notz = {c: r for c, r in core.items() if 1094 <= int(c) <= 1199}
    groups: dict[str, list[str]] = {}
    for code, record in sorted(notz.items()):
        groups.setdefault(str(record.get("type_code")), []).append(f"{code}:{record.get('name')}")
    for kind, names in sorted(groups.items()):
        print(f"  -- {kind} ({len(names)}): " + "; ".join(names))

    print("\n=== spot checks ===")
    for code in ("01166", "01135", "01157", "01161", "01171", "01182", "01104"):
        record = merged.get(code)
        print(f"  [{code}] " + (json.dumps({k: record[k] for k in ("name", "type_code", "real_text", "victory", "enemy_fight", "health", "doom", "clues") if k in record}, ensure_ascii=False)[:300] if record else "MISSING"))


if __name__ == "__main__":
    main()
