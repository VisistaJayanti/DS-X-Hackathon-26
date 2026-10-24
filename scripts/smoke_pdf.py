"""Robustness check: run stages 1-4 on text EXTRACTED FROM THE RENDERED PDFs (not the clean source text).

Usage: python scripts/smoke_pdf.py   (run data/render_documents.py first)
"""
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("PP_MODE", "offline")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from keeper.docs import pdf_to_text  # noqa: E402
from keeper.stages import extract, gaps, intake, rules  # noqa: E402


def pdf_text(path):
    return pdf_to_text(Path(path).read_bytes())


ok = 0
cases = sorted((ROOT / "data" / "cases").glob("*.json"))
for p in cases:
    c = json.loads(p.read_text(encoding="utf-8"))
    for d in c["documents"]:
        d["text"] = pdf_text(ROOT / "data" / "documents" / c["case_id"] / f"{d['doc_id']}.pdf")
    m = []
    i, _, _ = intake.run(c, m, use_llm=False)
    e, _, _ = extract.run(c, i, m, use_llm=False)
    r, _, _ = rules.run(c, i, e, m, use_llm=False)
    g, _, _ = gaps.run(c, e, r)
    lab = c["labels"]
    good = (r["ranking"][0] in lab["correct_pathways"] and sorted(x["code"] for x in g["gaps"]) == lab["gaps"]
            and g["evidence_sufficient"] == lab["evidence_sufficient"])
    ok += good
    if not good:
        print(f"BAD {c['case_id']} {c['title'][:55]} | rank={r['ranking'][:2]} gaps={[x['code'] for x in g['gaps']]}")
print(f"{ok}/{len(cases)} cases correct when reading the PDFs")
