"""Extract the official rulebooks and campaign guides to plain text.

The PDFs inside the asset pack are the authoritative rules source, so they get
turned into text under reference/ where they can be searched and diffed.

Run:  python tools/extract_pdfs.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from pypdf import PdfReader

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

PACK = Path(r"C:\Users\假烟桑··\Desktop\一步到胃") / "ahlcg图包一步到胃版"
PDF_DIR = PACK / "Mods" / "PDF"
OUT = Path(__file__).resolve().parents[1] / "reference" / "pdf"

WANTED = {
    "night_of_the_zealot_campaign_guide.txt": "nightofthezealotcampaignguidepdf",
    "rules_ahc26.txt": "ahc26rulesinsertpdf",
    "rules_ahc36.txt": "ahc36rulesinsertpdf",
}


def find_pdf(fragment: str) -> Path | None:
    for path in PDF_DIR.glob("*.PDF"):
        if fragment in path.name.lower():
            return path
    return None


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for out_name, fragment in WANTED.items():
        src = find_pdf(fragment)
        if src is None:
            print(f"!! not found: {fragment}")
            continue
        reader = PdfReader(str(src))
        pages = []
        for i, page in enumerate(reader.pages, start=1):
            try:
                text = page.extract_text() or ""
            except Exception as exc:  # pragma: no cover - defensive
                text = f"[extraction failed: {exc}]"
            pages.append(f"\n===== page {i} =====\n{text}")
        body = "".join(pages)
        (OUT / out_name).write_text(body, encoding="utf-8")
        print(f"=== {out_name}: {len(reader.pages)} pages, {len(body):,} chars -> {OUT / out_name}")
        print("    first 400 chars:", " | ".join(body[:400].split())[:400])


if __name__ == "__main__":
    main()
