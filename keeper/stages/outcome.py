"""Outcome stage: Retain, Recover or Transition, with the window that matters for each.

  retain          - covered (or at risk) and a pathway may keep them covered: answer the notice by its deadline
  recover         - already dropped for paperwork, still inside the reconsideration window: send the missing
                    papers, possibly without a new application
  recover_expired - dropped for paperwork, window closed: route to a new application (and to transition if needed)
  transition      - the evidence suggests the member may no longer qualify (a reported change, or no pathway):
                    move them to the right next coverage before a gap opens

Program-agnostic: window lengths, triggers, destinations and citations come from the pack's `reconsideration`
and `transitions` sections. The tool never decides eligibility; it says what the evidence suggests.
"""
import calendar
from datetime import date, timedelta

from .. import config, rulebook


def _d(s):
    return date.fromisoformat(s) if s else None


def _month_shift(d, n):
    y, m = divmod(d.month - 1 + n, 12)
    return date(d.year + y, m + 1, 1)


def window_for(spec, coverage_end, change):
    """Next-coverage window for a transition trigger."""
    if spec["kind"] == "medicare_iep":
        bday = _d(change.get("date")) if change else None
        if not bday:
            return None
        start = _month_shift(bday, -spec["months_before"])
        last = _month_shift(bday, spec["months_after"])
        end = last.replace(day=calendar.monthrange(last.year, last.month)[1])
        return {"opens": start.isoformat(), "closes": end.isoformat(), "avoid_gap_by": bday.isoformat(), "rule_id": spec["rule_id"],
                "label": "Medicare initial enrollment period"}
    if not coverage_end:
        return None
    return {"opens": (coverage_end - timedelta(days=spec.get("days_before", 0))).isoformat(),
            "closes": (coverage_end + timedelta(days=spec["days_after"])).isoformat(),
            "avoid_gap_by": coverage_end.isoformat(), "rule_id": spec["rule_id"],
            "advance_rule_id": spec.get("advance_rule_id"), "label": "Special enrollment window"}


def _transition(case, member, cov, changes, gaps_out, recon_info=None):
    tr = rulebook.active().get("transitions")
    if not tr:
        return None
    change = changes[0] if changes else None
    trig_key = change["type"] if change else "no_pathway"
    trig = tr["triggers"][trig_key]
    dl = gaps_out.get("deadline") or {}
    coverage_end = (_d(cov.get("expected_end_date")) or _d(cov.get("termination_date")) or _d(change.get("date") if change else None)
                    or _d(dl.get("due")))
    win = window_for(trig["window"], coverage_end, change)
    opts = [dict(id=o, **tr["options"][o]) for o in trig["options"]]
    lang = member.get("language", "en")
    label = trig["label"].get(lang, trig["label"]["en"])
    docs = trig.get("documents", [])
    handoff = (f"Warm hand-off for a navigator: {member['name']} (prefers {config.LANGUAGES.get(lang, lang)}). "
               f"Trigger: {trig['label']['en']}{' on ' + change['date'] if change and change.get('date') else ''}. "
               f"Coverage expected to end: {coverage_end.isoformat() if coverage_end else 'unknown'}. "
               + (f"To avoid a gap, enrol by {win['avoid_gap_by']}; window closes {win['closes']}. " if win else "")
               + "Review these options neutrally (member chooses): " + "; ".join(o["name"] for o in opts) + ". "
               + "Documents to gather: " + "; ".join(docs) + ".")
    return {"trigger": trig_key, "trigger_label": label, "trigger_rule_id": trig["rule_id"], "change": change,
            "coverage_end": coverage_end.isoformat() if coverage_end else None, "window": win, "options": opts, "documents": docs,
            "handoff_note": handoff, "neutral_routing_note": tr["neutral_routing_note"], "after_recover": recon_info}


def run(case, rules_out, gaps_out):
    member = case["member"]
    cov = member.get("coverage", {}) or {}
    status = cov.get("status", "active")
    pack = rulebook.active()
    recon = pack.get("reconsideration")
    triggers = (pack.get("transitions") or {}).get("triggers", {})
    changes = [c for c in member.get("reported_changes", []) if c.get("type") in triggers]
    no_pathway = rules_out["ranking"] == ["NONE"]
    out = {"coverage_status": status, "termination_date": cov.get("termination_date"),
           "termination_reason": cov.get("termination_reason"), "reasons": []}

    if status == "terminated_procedural" and recon:
        term = _d(cov["termination_date"])
        end = term + timedelta(days=recon["window_days"])
        left = (end - config.AS_OF).days
        since = (config.AS_OF - term).days
        out["reconsideration"] = {"window_days": recon["window_days"], "termination_date": term.isoformat(), "days_since": since,
                                  "ends": end.isoformat(), "days_left": left, "rule_id": recon["rule_id"],
                                  "ask_third_party_by": (end - timedelta(days=5)).isoformat(),
                                  "related_rules": recon.get("related_rules", []), "reinstatement_note": recon.get("reinstatement_note")}
        if left >= 0:
            out.update(outcome="recover", key_date=end.isoformat(),
                       deadline={"due": end.isoformat(), "days_left": left, "rule_id": recon["rule_id"],
                                 "label": f"Reconsideration period ends ({recon['window_days']} days after termination)",
                                 "urgency": "critical" if left <= 7 else "soon" if left <= 21 else "ok"})
            out["reasons"].append(f"Coverage ended {term.isoformat()} for paperwork ({cov.get('termination_reason', 'not stated')}); "
                                  f"{since} days ago, inside the {recon['window_days']}-day reconsideration period.")
            if changes:
                out["transition"] = _transition(case, member, cov, changes, gaps_out)
        else:
            out.update(outcome="recover_expired", key_date=end.isoformat(),
                       deadline={"due": end.isoformat(), "days_left": left, "rule_id": recon["rule_id"],
                                 "label": "Reconsideration period ended", "urgency": "overdue"})
            out["reasons"].append(f"Coverage ended {term.isoformat()}; the {recon['window_days']}-day reconsideration period ended "
                                  f"{end.isoformat()} ({-left} days ago). Route to a new application.")
            if changes or no_pathway:
                out["transition"] = _transition(case, member, cov, changes, gaps_out)
        return out, "deterministic", None

    if changes or no_pathway or status == "terminated_ineligible":
        t = _transition(case, member, cov, changes, gaps_out)
        if t:
            w = t["window"] or {}
            out.update(outcome="transition", transition=t, key_date=w.get("closes"),
                       deadline={"due": w.get("closes"), "avoid_gap_by": w.get("avoid_gap_by"),
                                 "days_left": (_d(w["closes"]) - config.AS_OF).days if w.get("closes") else None,
                                 "rule_id": w.get("rule_id"), "label": w.get("label", "Next-coverage window"),
                                 "urgency": "soon"})
            out["reasons"].append(f"Evidence suggests the member may no longer qualify: {t['trigger_label']}. The agency decides; "
                                  "a navigator confirms before anything changes.")
            return out, "deterministic", None

    dl = gaps_out.get("deadline") or {}
    out.update(outcome="retain", key_date=dl.get("due"), deadline=dl)
    out["reasons"].append("Covered or at risk; answer the notice by its deadline.")
    return out, "deterministic", None
