"""Sequential orchestrator. Each stage's input summary, output, engine, model calls and timing are recorded
in a trace so the UI can show every agent's work."""
import time

import json
from pathlib import Path

from . import config, risk, rulebook
from .stages import draft, extract, gaps, intake, outreach, rules, verify

ROSTER = Path(__file__).resolve().parent.parent / "data" / "roster.json"


def roster_member(case):
    if ROSTER.exists():
        for m in json.loads(ROSTER.read_text(encoding="utf-8")):
            if m.get("case_id") == case.get("case_id"):
                return m
    return None

STAGES = [
    ("risk", "Risk flag", "Why this member could lose coverage over paperwork"),
    ("outreach", "Outreach", "Channel + message in the member's language"),
    ("intake", "Intake", "Classify each document"),
    ("extract", "Extraction", "Pull facts with document/line quotes"),
    ("rules", "Rules", "Evaluate every pathway against the cited rulebook"),
    ("gaps", "Gap", "What's missing, how to fix it, the deadline"),
    ("followup", "Follow-up", "Exactly what to send / collect (SMS photo, CHW checklist)"),
    ("draft", "Drafting", "Packet, request letter, member explanation"),
    ("verify", "Verifier", "Drop any claim without a quote + rule"),
    ("translate", "Translation", "Member explanation in their language"),
]


def run(case, use_llm=None, use_verifier=True, lang=None, on_event=None):
    """Run all stages. Returns the trace dict. on_event(dict) is called as each stage starts/finishes."""
    rulebook.use(case.get("pack"))
    use_llm = (config.MODE != "offline") if use_llm is None else use_llm
    lang = lang or case["member"].get("language", "en")
    trace = {"case_id": case.get("case_id"), "mode": config.MODE, "as_of": config.AS_OF.isoformat(), "stages": [],
             "use_verifier": use_verifier, "language": lang}
    emit = on_event or (lambda e: None)
    out = {}

    def stage(key, fn):
        meta = next(s for s in STAGES if s[0] == key)
        emit({"event": "start", "stage": key, "label": meta[1]})
        meter, t0 = [], time.time()
        result, engine, note = fn(meter)
        ms = int((time.time() - t0) * 1000)
        rec = {"key": key, "label": meta[1], "desc": meta[2], "engine": engine, "note": note, "ms": ms,
               "llm_calls": meter, "cost": round(sum(m["cost"] for m in meter), 5),
               "cached_calls": sum(m["cached"] for m in meter), "output": result}
        trace["stages"].append(rec)
        out[key] = result
        emit({"event": "done", "stage": key, "record": rec})
        return result

    member = roster_member(case)

    def do_risk(m):
        if not member:
            return {"walk_in": True, "note": "Walk-in case: no plan roster record, so no risk score."}, "deterministic", None
        return dict(risk.score(member), member=member), "deterministic", None

    def do_outreach(m):
        who = member or dict(case["member"], member_id=None, has_mobile=True, sms_opt_in=False, preferred_channel="phone")
        return outreach.initial(who, gaps.deadline(case["member"]), m, use_llm), "deterministic", None

    stage("risk", do_risk)
    stage("outreach", do_outreach)
    stage("intake", lambda m: intake.run(case, m, use_llm))
    stage("extract", lambda m: extract.run(case, out["intake"], m, use_llm))
    stage("rules", lambda m: rules.run(case, out["intake"], out["extract"], m, use_llm))
    stage("gaps", lambda m: gaps.run(case, out["extract"], out["rules"]))
    who = member or dict(case["member"], sms_opt_in=False)
    stage("followup", lambda m: (outreach.followup(who, out["gaps"], m, use_llm), "deterministic", None))
    stage("draft", lambda m: draft.run(case, out["intake"], out["extract"], out["rules"], out["gaps"], m, use_llm))
    if use_verifier:
        stage("verify", lambda m: verify.run(case, out["extract"], out["rules"], out["gaps"], out["draft"], m, use_llm))
        final = out["verify"]["verified"]
    else:
        final = {k: out["draft"][k] for k in ("packet", "request", "member_en")}

    def tr(m):
        sents, eng = draft.translate(final["member_en"], lang, m, use_llm)
        return {"language": lang, "sentences": sents}, eng, None

    stage("translate", tr)
    trace["final"] = dict(final, member=out["translate"])
    trace["summary"] = {
        "ranking": out["rules"]["ranking"],
        "best_pathway": out["gaps"]["best_pathway"],
        "pack": rulebook.active()["id"],
        "risk_score": out["risk"].get("score"),
        "evidence_sufficient": out["gaps"]["evidence_sufficient"],
        "gaps": [g["code"] for g in out["gaps"]["gaps"]],
        "deadline": out["gaps"]["deadline"],
        "latency_ms": sum(s["ms"] for s in trace["stages"]),
        "cost_usd": round(sum(s["cost"] for s in trace["stages"]), 5),
        "llm_calls": sum(len(s["llm_calls"]) for s in trace["stages"]),
        "engines": {s["key"]: s["engine"] for s in trace["stages"]},
    }
    emit({"event": "complete", "summary": trace["summary"]})
    return trace
