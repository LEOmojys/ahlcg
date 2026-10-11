import re, sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
rules = Path("reference/pdf/rules_reference_core.txt").read_text(encoding="utf-8")

def show(title, pattern, width=1500, limit=2):
    print("\n" + "=" * 92)
    print("===", title)
    for i, m in enumerate(re.finditer(pattern, rules, re.IGNORECASE)):
        if i >= limit:
            break
        print("-" * 92)
        print(" ".join(rules[m.start(): m.start() + width].split())[:width])

show("Deckbuilding (size + weaknesses)", r"\nDeckbuilding\n", 2000, 1)
show("Investigator Deck", r"Investigator Deck", 1200, 1)
show("basic weakness mentions", r"basic weakness", 500, 3)
