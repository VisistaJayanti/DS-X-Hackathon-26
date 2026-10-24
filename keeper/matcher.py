"""Feature 2: match a member and their documents to policy packs.

Each pack's pack.json has an `eligibility` block:
    tier, countries, regions, nationalities, require_abroad, age_min, age_max,
    valid_from, valid_to, min_coverage_months, max_coverage_months, (+ *_rule ids, *_note, *_keywords)
Every criterion is scored pass / warn / fail / unknown with a reason, the rule it comes from, and a fix.
Profile values come first; facts read from the documents fill gaps (e.g. date of birth from a passport).
"""
import json
import re
from datetime import date

from . import config, doccheck, geo, rulebook

TIERS = {"commercial": "Commercial", "ivf": "IVF / fertility", "medicaid": "Medicaid", "medicare": "Medicare"}
BLOCKING = {"tier", "country", "region", "nationality", "abroad", "age"}
STATE_ABBR = {"ma": "massachusetts", "mass": "massachusetts", "ny": "new york", "ca": "california", "tx": "texas",
              "fl": "florida", "nj": "new jersey", "ri": "rhode island", "ct": "connecticut", "nh": "new hampshire"}
POINTS = {"pass": 10, "warn": 3, "unknown": 0, "fail": -25}


def _d(s):
    try:
        return date.fromisoformat(s) if s else None
    except ValueError:
        return None


def _months(a, b):
    return (b.year - a.year) * 12 + (b.month - a.month) + (1 if b.day >= a.day else 0)


def _doc_hit(documents, pattern):
    return doccheck._find_in_docs(documents, pattern) if pattern and documents else None


def _c(criterion, status, title, detail, rule_id=None, fix="", source=None):
    return {"criterion": criterion, "status": status, "title": title, "detail": detail, "rule_id": rule_id,
            "fix": fix, "source": source}


def evaluate(pack, case, facts=None):
    el = pack.get("eligibility")
    if not el:
        return None
    prof = case.get("member", {})
    docs = case.get("documents", [])
    facts = facts if facts is not None else doccheck.extract_facts(docs)
    out = []

    # Tier --------------------------------------------------------------------------------------
    want = (prof.get("tier") or "").lower()
    if not want:
        out.append(_c("tier", "unknown", "No insurance tier chosen", "Pick a tier to narrow the match.",
                      fix="Choose commercial, IVF, Medicaid or Medicare in the form."))
    elif want == el["tier"]:
        out.append(_c("tier", "pass", f"Tier: {TIERS.get(want, want)}", "The policy is in the tier you chose."))
    else:
        out.append(_c("tier", "fail", "Different insurance tier",
                      f"You chose {TIERS.get(want, want)}; this policy is {TIERS.get(el['tier'], el['tier'])}.",
                      fix="Only consider this policy if you meant to look at this tier."))

    # Country of residence -----------------------------------------------------------------------
    country = geo.to_code(prof.get("country")) or (prof.get("country") or "").upper() or None
    if el.get("countries"):
        if not country:
            out.append(_c("country", "unknown", "Country not given", "This policy is limited to " +
                          ", ".join(geo.name(c) for c in el["countries"]) + ".", fix="Enter your country of residence."))
        elif country in el["countries"]:
            out.append(_c("country", "pass", f"Lives in {geo.name(country)}", "Country of residence is covered."))
        else:
            out.append(_c("country", "fail", "Country not covered",
                          f"This policy covers {', '.join(geo.name(c) for c in el['countries'])}, not {geo.name(country) or country}.",
                          fix="Look at policies for your country of residence."))
    regions = el.get("regions") or []
    if regions:
        reg = (prof.get("region") or "").strip().lower()
        reg = STATE_ABBR.get(reg, reg)
        if not reg:
            out.append(_c("region", "unknown", "State / region not given", "This policy is limited to " + ", ".join(regions) + ".",
                          fix="Enter your state or region."))
        elif reg in (r.lower() for r in regions):
            out.append(_c("region", "pass", f"Region: {prof.get('region')}", "Region is covered."))
        else:
            out.append(_c("region", "fail", "Region not covered", f"This policy only covers {', '.join(regions)}.",
                          fix="Look at policies for your state or region."))

    # Nationality --------------------------------------------------------------------------------
    pname = prof.get("name") or ""
    nat = geo.to_code(prof.get("nationality"))
    nat_src = None
    if not nat:
        f = next((x for x in doccheck.member_facts(facts, pname, "nationality") if len(str(x["value"])) == 2), None)
        if f:
            nat, nat_src = f["value"], f
    if el.get("nationalities"):
        if not nat:
            out.append(_c("nationality", "unknown", "Nationality not given", el.get("nationality_note", ""),
                          el.get("nationality_rule"), "Enter your nationality or upload a passport."))
        elif nat in el["nationalities"]:
            out.append(_c("nationality", "pass", f"Nationality: {geo.name(nat)}", "Meets the nationality rule.",
                          el.get("nationality_rule"), source=nat_src))
        else:
            hit = _doc_hit(docs, el.get("nationality_exception_keywords"))
            if hit:
                out.append(_c("nationality", "warn", "Qualifies only through an exception", el.get("nationality_note", ""),
                              el.get("nationality_rule"), "Make sure the residence document is current and shows the start date.", hit))
            else:
                out.append(_c("nationality", "fail", "Nationality rule not met",
                              f"{geo.name(nat)} nationality. {el.get('nationality_note', '')}", el.get("nationality_rule"),
                              "If you have lawful permanent residence, upload that document.", nat_src))
    if el.get("require_abroad"):
        if nat and country:
            ok = nat != country
            out.append(_c("abroad", "pass" if ok else "fail", "Living abroad" if ok else "Not living abroad",
                          f"Nationality {geo.name(nat)}, living in {geo.name(country)}." +
                          ("" if ok else " This policy is for people living outside their home country."),
                          el.get("abroad_rule"), "" if ok else "Look at domestic plans in your country instead.", nat_src))
        else:
            out.append(_c("abroad", "unknown", "Can't tell if you live abroad", el.get("nationality_note", ""),
                          el.get("abroad_rule"), "Enter both nationality and country of residence."))

    # Age ----------------------------------------------------------------------------------------
    dob, dob_src = _d(prof.get("dob")), None
    if not dob and prof.get("age") in (None, ""):
        f = next(iter(doccheck.member_facts(facts, pname, "dob")), None)
        if f:
            dob, dob_src = _d(f["value"]), f
    on = _d(prof.get("coverage_start")) or config.AS_OF
    lo, hi = el.get("age_min"), el.get("age_max")
    if dob is None and prof.get("age") not in (None, ""):
        age = int(prof["age"])
    else:
        age = doccheck.doc_age(dob, on) if dob else None
    if age is None:
        if lo or hi:
            out.append(_c("age", "unknown", "Age unknown", "Enter a date of birth or upload a document that shows it.",
                          el.get("age_rule"), "Add your date of birth."))
    else:
        rng = f"{lo if lo is not None else 0}–{hi if hi is not None else 'any'}"
        if (lo is None or age >= lo) and (hi is None or age <= hi):
            out.append(_c("age", "pass", f"Age {age}", f"Within the policy's range ({rng}) on {on.isoformat()}.",
                          el.get("age_rule"), source=dob_src))
        else:
            hit = _doc_hit(docs, el.get("age_exception_keywords"))
            if hit:
                out.append(_c("age", "warn", f"Age {age}: outside range, possible exception",
                              f"Range is {rng}. {el.get('age_exception_note', '')}", el.get("age_rule"),
                              "Make sure the document proving the exception is included and current.", hit))
            else:
                out.append(_c("age", "fail", f"Age {age} is outside {rng}",
                              f"On {on.isoformat()} the member is {age}. {el.get('age_exception_note', '')}".strip(),
                              el.get("age_rule"),
                              "Check the date of birth. If it's correct, this policy likely doesn't apply"
                              + (", unless you have documents for the exception." if el.get("age_exception_note") else "."),
                              dob_src))

    # Timeline -----------------------------------------------------------------------------------
    start, end = _d(prof.get("coverage_start")), _d(prof.get("coverage_end"))
    vf, vt = _d(el.get("valid_from")), _d(el.get("valid_to"))
    if not start:
        out.append(_c("timeline", "unknown", "No coverage dates", el.get("timeline_note", ""),
                      fix="Enter the coverage start (and end) dates you need."))
    else:
        problems, warns = [], []
        if vf and (end or start) < vf:
            problems.append(f"the policy only starts on {vf.isoformat()}")
        elif vf and start < vf:
            warns.append(f"the policy starts on {vf.isoformat()}, after your requested start")
        if vt and start > vt:
            problems.append(f"the policy ended on {vt.isoformat()}")
        months = _months(start, end) if end and end > start else None
        mn, mx = el.get("min_coverage_months"), el.get("max_coverage_months")
        if months is not None and mn and months < mn:
            problems.append(f"{months} months requested, minimum is {mn}")
        if months is not None and mx and months > mx:
            warns.append(f"{months} months requested; this policy renews every {mx} months")
        status = "fail" if problems else "warn" if warns else "pass"
        detail = "; ".join(problems + warns) or f"Coverage from {start.isoformat()}" + (f" to {end.isoformat()}" if end else "") + " fits."
        if el.get("timeline_note"):
            detail += f" ({el['timeline_note']})"
        fix = {"fail": "Adjust the coverage dates to fit the policy period and minimum term.",
               "warn": "Plan for the renewal or start date shown.", "pass": ""}[status]
        out.append(_c("timeline", status, "Timeline", detail, el.get("coverage_rule"), fix))

        # Waiting period: a planned event in the documents (e.g. an IVF cycle) must fall after start + N months.
        wp = el.get("waiting_period_months")
        if wp:
            from .textutil import add_months, find_dates
            earliest = add_months(start, wp)
            hit = _doc_hit(docs, el.get("waiting_event_keywords"))
            label = el.get("waiting_event_label", "treatment")
            planned = find_dates(hit["quote"]) if hit else []
            if not hit or not planned:
                out.append(_c("waiting_period", "warn", "Waiting period",
                              f"The {label} can be covered from {earliest.isoformat()} ({wp} months after coverage starts). "
                              "No planned date was found in the documents.", el.get("waiting_rule"),
                              f"Make sure the {label} is scheduled on or after {earliest.isoformat()}.", hit))
            elif planned[-1] < earliest:
                out.append(_c("waiting_period", "fail", "Planned during the waiting period",
                              f"The {label} is planned for {planned[-1].isoformat()}, but cover for it starts "
                              f"{earliest.isoformat()} ({wp} months after {start.isoformat()}).", el.get("waiting_rule"),
                              f"Reschedule the {label} to {earliest.isoformat()} or later, or ask the insurer whether "
                              "earlier continuous coverage counts toward the waiting period.", hit))
            else:
                out.append(_c("waiting_period", "pass", "Waiting period met",
                              f"The {label} ({planned[-1].isoformat()}) is after the waiting period ends ({earliest.isoformat()}).",
                              el.get("waiting_rule"), source=hit))

    score = sum(POINTS[c["status"]] for c in out)
    # Tier, place, nationality and age decide whether a policy applies at all. Timeline and waiting-period
    # problems are fixable (change dates, reschedule), so they become flags instead of ruling the policy out.
    worst = "no_match" if any(c["status"] == "fail" and c["criterion"] in BLOCKING for c in out) else \
        "possible" if any(c["status"] != "pass" for c in out) else "match"
    return {"pack": pack["id"], "name": pack["name"], "tier": el["tier"], "illustrative": pack.get("illustrative", False),
            "runnable": pack.get("runnable", False), "status": worst, "score": score, "criteria": out}


def all_packs():
    packs = []
    for p in sorted(rulebook.PACKS.iterdir()):
        if (p / "pack.json").exists():
            packs.append(json.loads((p / "pack.json").read_text(encoding="utf-8")))
    return packs


def match(case):
    """Rank every pack for this case: best match first."""
    facts = doccheck.extract_facts(case.get("documents", []))
    results = [r for r in (evaluate(p, case, facts) for p in all_packs()) if r]
    rank = {"match": 0, "possible": 1, "no_match": 2}
    results.sort(key=lambda r: (rank[r["status"]], -r["score"]))
    return {"case_id": case.get("case_id"), "results": results, "facts": facts,
            "best": results[0]["pack"] if results and results[0]["status"] != "no_match" else None}
