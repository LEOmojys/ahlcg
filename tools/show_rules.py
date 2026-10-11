import re, sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
rules = Path("reference/pdf/rules_reference_core.txt").read_text(encoding="utf-8")

def show(title, pattern, limit=3, width=1300):
    print("\n" + "=" * 95)
    print("===", title)
    for i, m in enumerate(re.finditer(pattern, rules, re.IGNORECASE)):
        if i >= limit:
            break
        print("-" * 95)
        print(" ".join(rules[m.start(): m.start() + width].split())[:width])

show("Enemy Phase detail", r"3\.1 Enemy phase begins", 1, 2200)
show("Exhaust (glossary)", r"\nExhaust\n", 1, 900)
show("Ready (glossary)", r"\nReady\n", 1, 900)
show("Attack of Opportunity", r"Attack of Opportunity", 1, 1200)
show("Enemy attacks / engages", r"An enemy attacks", 2, 700)
show("Hunter", r"\nHunter\n", 1, 700)
