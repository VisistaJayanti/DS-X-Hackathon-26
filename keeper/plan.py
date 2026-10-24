"""Plan view: ranked at-risk roster, case pipeline status, simple retention numbers (all synthetic)."""
import hashlib
import json
from pathlib import Path

from . import risk

ROOT = Path(__file__).resolve().parent.parent
STATUSES = ["flagged", "contacted", "documents_received", "packet_ready", "submitted"]
# Illustrative assumption, NOT a sourced figure: average Medicaid managed-care capitation per member per month.
ASSUMED_PMPM_USD = 600


def _status(member_id):
    """Deterministic synthetic progress for demo purposes."""
    h = int(hashlib.md5(member_id.encode()).hexdigest(), 16) % 100
    return STATUSES[0 if h < 30 else 1 if h < 55 else 2 if h < 75 else 3 if h < 90 else 4]


MARIA_TIMELINE = [
    {"day": 0, "event": "MassHealth mails RFI (in English)"},
    {"day": 3, "event": "Coverage Keeper flags Maria: risk 8.0 (English notice / Spanish speaker, possible caregiver exemption, not reached in 90 days)"},
    {"day": 4, "event": "Text + phone call in Spanish; screener questions surface caregiving for her mother"},
    {"day": 9, "event": "Maria texts photos: her caregiver statement and her mother's neurology letter"},
    {"day": 12, "event": "Packet drafted; gap caught (letter doesn't state a disability); request sent to her mother's doctor"},
    {"day": 18, "event": "Planned: updated doctor letter inserted, coordinator approves, packet submitted (deadline day 30)"},
]


def plan(top_k=risk.TOP_K_DEFAULT):
    everyone = json.loads((ROOT / "data" / "roster.json").read_text(encoding="utf-8"))
    roster = [m for m in everyone if m.get("group", "at_risk") == "at_risk"]
    ranked = risk.rank_roster(roster)
    rows = []
    for s in ranked:
        m = s["member"]
        flagged = s["rank"] <= top_k and s["score"] > 0
        st = ("packet_ready" if m["member_id"] == "M0001" else _status(m["member_id"])) if flagged else None
        rows.append({"rank": s["rank"], "member_id": m["member_id"], "name": m["name"], "age": m["age"], "city": m["city"],
                     "language": m["language"], "score": s["score"], "reasons": s["reasons"][:3], "days_left": s["days_left"],
                     "due": s["due"], "flagged": flagged, "status": st, "case_id": m.get("case_id"),
                     "channel": m.get("preferred_channel")})
    flagged = [r for r in rows if r["flagged"]]
    counts = {k: sum(r["status"] == k for r in flagged) for k in STATUSES}
    done = counts["packet_ready"] + counts["submitted"]
    return {
        "top_k": top_k, "rows": rows, "pipeline": counts,
        "retention": {"members": len(rows), "flagged": len(flagged),
                      "on_track": done, "at_risk_unresolved": len(flagged) - done,
                      "assumed_pmpm_usd": ASSUMED_PMPM_USD,
                      "annual_revenue_on_track_usd": done * ASSUMED_PMPM_USD * 12,
                      "note": "PMPM capitation is an illustrative assumption, not a sourced figure. Statuses are synthetic. "
                              "Members are synthetic; their city and language mix and base rates are calibrated to public "
                              "CMS (MassHealth renewal outcomes) and ACS data."},
        "maria_timeline": MARIA_TIMELINE,
        **recover_transition_groups(everyone, done),
    }


def recover_transition_groups(everyone, retained_on_track):
    """Recoverable (dropped for paperwork, inside the reconsideration window) and Transition (likely to lose eligibility)."""
    from datetime import date, timedelta

    from . import config, rulebook
    from .stages.outcome import window_for

    recon = rulebook.active().get("reconsideration")
    trig = (rulebook.active().get("transitions") or {}).get("triggers", {})
    recover, transition = [], []
    for m in everyone:
        cov = m.get("coverage") or {}
        if m.get("group") == "recover" and recon:
            term = date.fromisoformat(cov["termination_date"])
            ends = term + timedelta(days=recon["window_days"])
            left = (ends - config.AS_OF).days
            recover.append({"member_id": m["member_id"], "name": m["name"], "language": m["language"], "case_id": m.get("case_id"),
                            "termination_date": cov["termination_date"], "reason": cov.get("termination_reason"),
                            "window_ends": ends.isoformat(), "days_left": left, "recoverable": left >= 0,
                            "status": ("expired: new application" if left < 0 else "packet_ready" if m.get("case_id") == "C47"
                                       else _status(m["member_id"]))})
        elif m.get("group") == "transition":
            ch = (m.get("reported_changes") or [{}])[0]
            t = trig.get(ch.get("type"))
            end = cov.get("expected_end_date")
            w = window_for(t["window"], date.fromisoformat(end) if end else None, ch) if t else None
            transition.append({"member_id": m["member_id"], "name": m["name"], "language": m["language"], "case_id": m.get("case_id"),
                               "trigger": t["label"]["en"] if t else ch.get("type"), "coverage_end": end,
                               "avoid_gap_by": (w or {}).get("avoid_gap_by"), "window_closes": (w or {}).get("closes"),
                               "handoff_done": m.get("case_id") == "C50" or int(hashlib.md5(m["member_id"].encode()).hexdigest(), 16) % 3 == 0})
    recover.sort(key=lambda r: (not r["recoverable"], r["days_left"]))
    transition.sort(key=lambda r: r["avoid_gap_by"] or "9999")
    recovered = sum(r["recoverable"] and r["status"] in ("packet_ready", "submitted") for r in recover)
    return {"recover": recover, "transition": transition,
            "outcomes": {"retained_on_track": retained_on_track, "recovered_on_track": recovered,
                         "recoverable_open": sum(r["recoverable"] for r in recover),
                         "transitioned_handoff_done": sum(r["handoff_done"] for r in transition),
                         "transition_pending": sum(not r["handoff_done"] for r in transition),
                         "note": "Estimates on synthetic data: statuses and hand-offs are simulated for the demo."}}
