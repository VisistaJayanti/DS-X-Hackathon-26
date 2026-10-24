"""Quick offline check of stages 1-4 against the labels. Usage: python scripts/smoke.py [case_id]"""
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("PP_MODE", "offline")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from keeper.stages import extract, gaps, intake, rules  # noqa: E402

cases = sorted((Path(__file__).resolve().parent.parent / "data" / "cases").glob("*.json"))
only = sys.argv[1] if len(sys.argv) > 1 else None
bad = 0
for p in cases:
    c = json.loads(p.read_text(encoding="utf-8"))
    if only and c["case_id"] != only:
        continue
    m = []
    i, _, _ = intake.run(c, m, use_llm=False)
    e, _, _ = extract.run(c, i, m, use_llm=False)
    r, _, _ = rules.run(c, i, e, m, use_llm=False)
    g, _, _ = gaps.run(c, e, r)
    lab = c["labels"]
    got_gaps = sorted(x["code"] for x in g["gaps"])
    ok = r["ranking"][0] in lab["correct_pathways"] and got_gaps == lab["gaps"] and g["evidence_sufficient"] == lab["evidence_sufficient"]
    bad += not ok
    if not ok or only:
        print(f"{'OK ' if ok else 'BAD'} {c['case_id']} {c['title'][:50]}")
        print(f"     rank={r['ranking'][:3]} want={lab['correct_pathways']} | gaps={got_gaps} want={lab['gaps']} | "
              f"suff={g['evidence_sufficient']} want={lab['evidence_sufficient']}")
        if only:
            print("  types:", [(d["doc_id"], d["doc_type"]) for d in i["documents"]])
            for f in e["facts"]:
                print("  ", {k: v for k, v in f.items() if k not in ("quote",)})
            for pw in r["pathways"]:
                if pw["status"] != "not_met" or only:
                    print("   ", pw["pathway"], pw["status"], pw["reasons"])
print(f"{len(cases) - bad}/{len(cases)} cases fully correct" if not only else "")
