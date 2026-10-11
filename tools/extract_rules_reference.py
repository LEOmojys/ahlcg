"""Extract the core Rules Reference and the FAQ, then answer a rules question from the source."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from pypdf import PdfReader

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

PACK = Path(r"C:\Users\假烟桑··\Desktop\一步到胃") / "ahlcg图包一步到胃版"
PDF_DIR = PACK / "Mods" / "PDF"
OUT = Path(__file__).resolve().parents[1] / "reference" / "pdf"
OUT.mkdir(parents=True, exist_ok=True)

TARGETS = {
    "rules_reference_core.txt": "E2D8F25E63B88D702B21B0DC",
    "faq_errata_v22.txt": "B74142001EA8F48FA67B68AC",
    "learn_to_play.txt": None,
}


def extract(path: Path) -> str:
    reader = PdfReader(str(path))
    chunks = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            chunks.append(f"\n===== page {i} =====\n" + (page.extract_text() or ""))
        except Exception as exc:
            chunks.append(f"\n===== page {i} (failed: {exc}) =====\n")
    return "".join(chunks)


def main() -> None:
    for out_name, token in TARGETS.items():
        if token is None:
            continue
        matches = [p for p in PDF_DIR.glob("*.PDF") if token.lower() in p.name.lower()]
        if not matches:
            print(f"!! no pdf matching {token}")
            continue
        body = extract(matches[0])
        (OUT / out_name).write_text(body, encoding="utf-8")
        print(f"=== {out_name}: {len(body):,} chars from {matches[0].name[:40]}")

    rules = (OUT / "rules_reference_core.txt").read_text(encoding="utf-8")

    print("\n" + "=" * 90)
    print("=== MYTHOS PHASE entry in the Rules Reference ===")
    for match in re.finditer(r"Mythos Phase", rules):
        start = match.start()
        print(rules[start : start + 1400].replace("\n", " | ")[:1400])
        print("-" * 90)
        break

    print("\n=== every mention of 'first round' ===")
    for match in re.finditer(r"first round", rules, re.IGNORECASE):
        snippet = rules[max(0, match.start() - 400) : match.start() + 400].replace("\n", " | ")
        print("  ...", snippet, "...")
        print("-" * 60)

    print("\n=== table of contents / headings ===")
    heads = re.findall(r"\n([A-Z][A-Za-z \-]{3,40})\n", rules)
    seen = []
    for head in heads:
        head = head.strip()
        if head not in seen:
            seen.append(head)
    print(", ".join(seen[:120]))


if __name__ == "__main__":
    main()
