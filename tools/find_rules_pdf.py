"""Locate the core rules reference among the PDFs bundled with the asset pack."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from pypdf import PdfReader

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

PACK = Path(r"C:\Users\假烟桑··\Desktop\一步到胃") / "ahlcg图包一步到胃版"
PDF_DIR = PACK / "Mods" / "PDF"
OUT = Path(__file__).resolve().parents[1] / "reference" / "pdf"

PROBES = ("神话阶段", "规则参考", "Mythos Phase", "Rules Reference", "调查阶段", "Learn to Play",
          "学习游戏", "参考手册", "阴谋", "毁灭标记")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for path in sorted(PDF_DIR.glob("*.PDF")):
        try:
            reader = PdfReader(str(path))
            first = (reader.pages[0].extract_text() or "")
        except Exception as exc:
            print(f"!! {path.name[:60]}: {type(exc).__name__} {exc}")
            continue
        flat = " ".join(first.split())
        hits = [probe for probe in PROBES if probe in first]
        label = " ".join(flat.split())[:150]
        print(f"{len(reader.pages):3d}p  {path.name[-28:]:<30} hits={hits}  {label}")
        if hits and ("神话阶段" in first or "Mythos Phase" in first or "规则参考" in first or "Rules Reference" in first):
            body = []
            for i, page in enumerate(reader.pages, start=1):
                try:
                    body.append(f"\n===== page {i} =====\n" + (page.extract_text() or ""))
                except Exception as exc:
                    body.append(f"\n===== page {i} (failed: {exc}) =====\n")
            target = OUT / f"rules_{path.name[-12:].replace('.', '_')}.txt"
            target.write_text("".join(body), encoding="utf-8")
            print(f"      -> saved {target} ({sum(len(b) for b in body):,} chars)")


if __name__ == "__main__":
    main()
