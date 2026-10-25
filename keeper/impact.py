"""Policy impact: run every dataset case under two policy packs with the rules engine (no AI) and compare.

Answers "what would change for these members if this policy applied instead?" in about a second. Names of
pathways differ between packs, so a change is judged by what happens to the member, not by the pathway's name.
"""
from collections import Counter

from . import pipeline, rulebook


def _result(case, pack):
    trace = pipeline.run(dict(case, pack=pack), use_llm=False)
    pathways = next(s["output"]["pathways"] for s in trace["stages"] if s["key"] == "rules")
    s = trace["summary"]
    best = next((p for p in pathways if p["pathway"] == s["best_pathway"]), None)
    return trace, {"pathway": best["name"] if best else None, "status": best["status"] if best else None,
                   "kind": best["kind"] if best else None, "reason": best["reasons"][0] if best else None,
                   "sufficient": s["evidence_sufficient"], "outcome": s["outcome"], "gaps": s["gaps"]}


def _change(a, b):
    if a["pathway"] and not b["pathway"]:
        return "loses"
    if b["pathway"] and not a["pathway"]:
        return "gains"
    if a["outcome"] != b["outcome"]:
        return "outcome"
    if (a["status"] == "met" and b["status"] != "met") or (a["sufficient"] and not b["sufficient"]):
        return "weaker"
    if (b["status"] == "met" and a["status"] != "met") or (b["sufficient"] and not a["sufficient"]):
        return "stronger"
    return "same"


def compare(cases, pack, base, save=None):
    """save(case_id, trace) is called with each case's trace under `pack`, so its case pages can show it."""
    rows = []
    try:
        for c in cases:
            _, before = _result(c, base)
            trace, after = _result(c, pack)
            if save:
                save(c["case_id"], trace)
            rows.append({"case_id": c["case_id"], "title": c["title"], "name": c["member"]["name"],
                         "language": c["member"].get("language", "en"), "base": before, "new": after, "change": _change(before, after)})
    finally:
        rulebook.use(None)  # the server reuses threads; leave the default pack active
    outcomes = {k: Counter(r[k]["outcome"] for r in rows) for k in ("base", "new")}
    return {"pack": pack, "base": base, "n": len(rows), "counts": Counter(r["change"] for r in rows), "outcomes": outcomes, "rows": rows}
