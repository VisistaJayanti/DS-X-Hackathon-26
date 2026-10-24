"""Stage 4 - Gap: what is missing or weak for the best pathway(s), the concrete fix, and the deadline."""
from datetime import date, timedelta

from .. import config, rulebook

def deadline(member):
    rec = member.get("notice_received_date")
    if not rec:
        return None
    due = date.fromisoformat(rec) + timedelta(days=rulebook.program()["response_window_days"])
    left = (due - config.AS_OF).days
    urgency = "overdue" if left < 0 else "critical" if left <= 7 else "soon" if left <= 14 else "ok"
    return {"notice_received": rec, "due": due.isoformat(), "days_left": left, "urgency": urgency, "rule_id": rulebook.program()["deadline_rule"],
            "ask_third_party_by": (due - timedelta(days=5)).isoformat()}


def run(case, extract_out, rules_out):
    facts = {f["fact_id"]: f for f in extract_out["facts"]}
    paths = {p["pathway"]: p for p in rules_out["pathways"]}
    ranking = rules_out["ranking"]
    gaps, seen = [], set()

    def add(g, pathway):
        if g["code"] in seen:
            return
        seen.add(g["code"])
        gc = rulebook.gap(g["code"])
        gaps.append({**g, "pathway": pathway, "ask": gc["ask"], "fix": gc["fix"]})

    if ranking == ["NONE"]:
        add({"code": "NO_QUALIFYING_PATHWAY", "detail": "No compliance or exemption pathway is met or partially supported.", "evidence": []}, None)
        for pid in (pw["id"] for pw in rulebook.pathways() if pw["evaluator"] == "threshold"):
            for g in paths[pid]["gaps"]:
                add(g, pid)
    else:
        for pid in ranking:
            for g in paths[pid]["gaps"]:
                add(g, pid)
        # Non-English documents that the leading pathway relies on.
        top_ev = set(paths[ranking[0]]["evidence"])
        for f in facts.values():
            if f["type"] == "doc_language" and any(facts[e]["doc_id"] == f["doc_id"] for e in top_ev if e in facts):
                add({"code": "DOC_TRANSLATION", "detail": f"{f['doc_id']} is in '{f.get('language')}'.", "evidence": [f["fact_id"]]}, ranking[0])

    top = paths.get(ranking[0])
    sufficient = bool(top and top["status"] == "met" and not any(g["pathway"] == ranking[0] and g["code"] != "DOC_TRANSLATION" for g in gaps))
    return {"gaps": gaps, "deadline": deadline(case["member"]), "evidence_sufficient": sufficient,
            "best_pathway": ranking[0], "resources": rulebook.active()["resources"] if ranking == ["NONE"] else []}, "deterministic", None
