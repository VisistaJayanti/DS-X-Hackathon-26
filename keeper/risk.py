"""Stage 0 - Risk flagging: rank plan members by risk of losing coverage for paperwork reasons.

Deliberately simple and explainable: a points score, each point with a human-readable reason.
Hand-set weights (not fit to the synthetic labels). Flags are used ONLY to offer help sooner - never to
deny, delay or deprioritise anyone's coverage or services.
"""
from datetime import date, timedelta

from . import config, rulebook

WEIGHTS = [
    ("returned_mail", 3.0, "Mail to this member was returned - they may never see the notice"),
    ("address_change_90d", 1.5, "Address changed in the last 90 days"),
    ("missed_prior_notices", 1.5, "Missed {v} earlier notice(s) (points per notice)"),
    ("language_mismatch", 2.0, "Notice sent in English; member prefers {lang}"),
    ("not_reached", 1.5, "No successful contact in 90 days"),
    ("no_portal", 0.5, "No online account to upload documents"),
    ("deadline_soon", 1.5, "Response due in {days} days"),
    ("exemption_hint", 1.0, "Plan data suggests a possible exemption ({hint}) the member may not know about"),
]
TOP_K_DEFAULT = 40


def features(m):
    due = date.fromisoformat(m["notice_received_date"]) + timedelta(days=rulebook.program()["response_window_days"])
    days = (due - config.AS_OF).days
    return {
        "returned_mail": float(m["returned_mail"]),
        "address_change_90d": float(m["address_change_90d"]),
        "missed_prior_notices": float(m["missed_prior_notices"]),
        "language_mismatch": float(m["language"] != m.get("notice_language", "en")),
        "not_reached": float(not m["reached_last_90d"]),
        "no_portal": float(not m["portal_account"]),
        "deadline_soon": float(days < 14),
        "exemption_hint": float(m.get("exemption_hint", "none") != "none"),
    }, days, due


def score(m):
    if not m.get("subject_to_requirement", True):
        return {"member_id": m["member_id"], "score": 0.0, "reasons": [], "days_left": None, "due": None,
                "note": "Not subject to the current renewal action"}
    f, days, due = features(m)
    reasons = []
    total = 0.0
    for key, w, text in WEIGHTS:
        pts = w * f[key]
        if pts:
            total += pts
            reasons.append({"points": pts, "text": text.format(v=int(f[key]), lang=config.LANGUAGES.get(m["language"], m["language"]),
                                                               days=days, hint=m.get("exemption_hint", "").replace("_", " "))})
    reasons.sort(key=lambda r: -r["points"])
    return {"member_id": m["member_id"], "score": round(total, 2), "reasons": reasons, "days_left": days, "due": due.isoformat()}


def rank_roster(roster):
    scored = [dict(score(m), member=m) for m in roster]
    scored.sort(key=lambda s: (-s["score"], s["days_left"] if s["days_left"] is not None else 999))
    for i, s in enumerate(scored, 1):
        s["rank"] = i
    return scored
