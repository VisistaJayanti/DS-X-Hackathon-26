"""Stage 3 - Rules: evaluate the facts against EVERY pathway in the active policy pack.

The engine is program-agnostic: each pack pathway names a generic evaluator plus its parameters
(thresholds, ages, windows). Thresholds, ages and dates are deterministic code. The one interpretive
question - does a clinician letter describe a qualifying condition that significantly impairs the
ability to comply? - goes to the LLM (with a deterministic fallback), and its answer must quote the letter.
"""
from datetime import date

from .. import config
from .. import docs as D
from .. import rulebook
from ..llm import LLMUnavailable, call_json
from ..textutil import add_months, age_on

STATUS_SCORE = {"met": 3, "insufficient": 2, "not_met": 0}
KIND_SCORE = {"out_of_scope": 3, "exemption": 2, "compliance": 1}
ADULT_RELATIONS = {"mother", "father", "brother", "sister", "husband", "wife", "grandmother", "grandfather", "spouse", "partner"}
CHILD_RELATIONS = {"son", "daughter", "child"}


def _result(pid, status, reasons, evidence=(), gaps=(), strength=1.0, extra=None):
    pw, r = rulebook.pathway(pid), rulebook.rule_for(pid)
    out = {"pathway": pid, "name": r["name"], "kind": pw["kind"], "rule_id": r["id"], "status": status,
           "reasons": list(reasons), "evidence": [f["fact_id"] for f in evidence if f], "gaps": list(gaps),
           "strength": strength, "needs_confirmation": r["needs_confirmation"]}
    if extra:
        out.update(extra)
    return out


def _gap(code, detail, evidence=()):
    return {"code": code, "detail": detail, "evidence": [f["fact_id"] for f in evidence if f]}


def _of(facts, *types):
    return [f for f in facts if f["type"] in types]


def _member_age(case, facts):
    dob = next((f for f in _of(facts, "member_dob") if f.get("date")), None)
    if dob:
        return age_on(date.fromisoformat(dob["date"]), config.AS_OF), dob
    return case["member"].get("age"), None


def _same_person(a, b):
    ta, tb = (a or "").lower().split(), (b or "").lower().split()
    return bool(ta and tb and ta[0] == tb[0])


# ------------------------------------------------------------ threshold pathways (hours / income)
def _monthly(facts, ftype, key, lookback, weekly_mult):
    """Best documented month inside / outside the review window, plus any weekly/estimated figure."""
    items = [f for f in _of(facts, ftype) if f.get(key) is not None]
    documented = [f for f in items if f.get("basis") in ("per_period", "monthly", None) and f.get("month")]
    weekly = [f for f in items if f.get("basis") in ("weekly", "estimate") or not f.get("month")]
    by_month = {}
    for f in documented:
        by_month.setdefault(f["month"], []).append(f)

    def best(d):
        if not d:
            return None
        m = max(d, key=lambda k: sum(f[key] for f in d[k]))
        return {"month": m, "total": round(sum(f[key] for f in d[m]), 2), "facts": d[m]}

    est = None
    if weekly:
        f = weekly[0]
        est = {"total": round(f[key] * (weekly_mult if f.get("basis") == "weekly" else 1.0), 2), "facts": [f]}
    return (best({m: v for m, v in by_month.items() if m in lookback}),
            best({m: v for m, v in by_month.items() if m not in lookback}), est)


def ev_threshold(ctx, pw):
    p, pid, facts, case = pw["params"], pw["id"], ctx["facts"], ctx["case"]
    req, unit = float(p["threshold"]), p["unit"]
    lookback = case["member"].get("lookback_months", [])
    cur = rulebook.program().get("currency", "USD")
    fmt = (lambda v: f"{v:g} hours") if unit == "hours" else (lambda v: f"${v:,.2f}" if cur == "USD" else f"{v:,.2f} {cur}")
    b_in, b_out, est = _monthly(facts, p["fact_type"], p["key"], lookback, p.get("weekly_multiplier", 1.0))
    if not (b_in or b_out or est):
        return _result(pid, "not_met", [f"No {'hours' if unit == 'hours' else 'income'} documentation provided."], strength=0)
    if b_in and est:
        a, b = b_in["total"], est["total"]
        if (a >= req) != (b >= req) and abs(a - b) / max(a, b) > p.get("conflict_tolerance", 0.15):
            ev = b_in["facts"] + est["facts"]
            return _result(pid, "insufficient", [f"Documents conflict: {fmt(a)} documented for {b_in['month']} vs about {fmt(b)}/month implied elsewhere."],
                           ev, [_gap("DOC_CONFLICT", f"{fmt(a)} in one document vs about {fmt(b)}/month in another; the {fmt(req)} line "
                                                     f"falls between them.", ev)], strength=0.6)
    if b_in:
        if b_in["total"] >= req:
            return _result(pid, "met", [f"{fmt(b_in['total'])} documented for {b_in['month']} (requirement: at least {fmt(req)})."],
                           b_in["facts"], extra={"computed": b_in["total"], "month": b_in["month"]})
        short = round(req - b_in["total"], 2)
        return _result(pid, "not_met", [f"Best documented month {b_in['month']}: {fmt(b_in['total'])}, {fmt(short)} short of {fmt(req)}."],
                       b_in["facts"], [_gap(p["short_gap"], f"{fmt(b_in['total'])} documented in {b_in['month']}; {fmt(short)} more needed.",
                                            b_in["facts"])], strength=0, extra={"computed": b_in["total"], "month": b_in["month"]})
    if est and est["total"] >= req:
        return _result(pid, "met", [f"Letter implies about {fmt(est['total'])}/month (no month-specific record)."], est["facts"],
                       strength=0.7, extra={"computed": est["total"]})
    if b_out and b_out["total"] >= req:
        return _result(pid, "insufficient", [f"{fmt(b_out['total'])} documented, but for {b_out['month']}, outside the review months "
                                             f"{', '.join(lookback)}."], b_out["facts"],
                       [_gap("OUTSIDE_LOOKBACK", f"Documents cover {b_out['month']}; need records for one of {', '.join(lookback)}.",
                             b_out["facts"])], strength=0.5)
    best = b_out or est
    return _result(pid, "not_met", [f"Only {fmt(best['total'])} documented."], best["facts"],
                   [_gap(p["short_gap"], f"{fmt(best['total'])} documented; {fmt(req - best['total'])} more needed.", best["facts"])], strength=0)


def _activity(ctx):
    pw = next((x for x in rulebook.pathways() if x["evaluator"] == "threshold" and x["params"]["unit"] == "hours"), None)
    if not pw:
        return None
    b_in, _, est = _monthly(ctx["facts"], pw["params"]["fact_type"], pw["params"]["key"],
                            ctx["case"]["member"].get("lookback_months", []), pw["params"].get("weekly_multiplier", 1.0))
    return b_in or est


# ------------------------------------------------------------ education
def ev_enrollment(ctx, pw):
    enr, pid = _of(ctx["facts"], "enrollment"), pw["id"]
    if not enr:
        return _result(pid, "not_met", ["No school enrollment document."], strength=0)
    f, st = enr[0], enr[0].get("status", "unspecified")
    if st in pw["params"]["accepted"]:
        return _result(pid, "met", [f"School states enrollment status: {st.replace('_', '-')}."], [f])
    if st == "less_than_half":
        return _result(pid, "not_met", ["School states less than half-time; see the combination pathway."], [f], strength=0)
    msg = "says 'part-time' but not whether it is at least half-time" if st == "part_time_unspecified" else "does not state an enrollment status"
    return _result(pid, "insufficient", [f"The school letter {msg}."], [f],
                   [_gap("ENROLLMENT_STATUS_UNSTATED", f"The school letter {msg}.", [f])], strength=0.6)


def ev_combination(ctx, pw):
    p, pid = pw["params"], pw["id"]
    enr, work = _of(ctx["facts"], "enrollment"), _activity(ctx)
    if not enr or not work:
        return _result(pid, "not_met", ["Needs both activity hours and less-than-half-time enrollment."], strength=0)
    f, st = enr[0], enr[0].get("status", "unspecified")
    if st in p["accepted_alone"]:
        return _result(pid, "not_met", ["Enrollment at this level counts on its own (education pathway)."], strength=0)
    if st == "less_than_half" and f.get("credits"):
        edu = round(f["credits"] * p["hours_per_credit_per_week"] * p["weeks_per_month"], 2)
        total = round(work["total"] + edu, 2)
        status = "met" if total >= p["threshold"] else "not_met"
        return _result(pid, status, [f"{work['total']:g} activity hours + {f['credits']:g} credits x {p['hours_per_credit_per_week']:g} x "
                                     f"{p['weeks_per_month']:g} = {edu:g} education hours -> {total:g} hours."],
                       work["facts"] + [f], strength=1.0 if status == "met" else 0, extra={"computed": total})
    return _result(pid, "insufficient", [f"{work['total']:g} activity hours documented, but the school letter gives no credit hours / status "
                                         f"to convert."], work["facts"] + [f],
                   [_gap("ENROLLMENT_STATUS_UNSTATED", "Need the school to state credit hours and enrollment status.", [f])], strength=0.6)


# ------------------------------------------------------------ caregiving / disability
def ev_dependent_child(ctx, pw):
    facts, pid, max_age = ctx["facts"], pw["id"], pw["params"]["max_age"]
    kids = [f for f in _of(facts, "child") if f.get("date")]
    kids += [f for f in _of(facts, "delivery") if f.get("date") and f.get("lives_with", True)]
    claims = [f for f in _of(facts, "care_claim") if (f.get("relation") or "").lower() in CHILD_RELATIONS]
    if kids:
        ages = [(age_on(date.fromisoformat(k["date"]), config.AS_OF), k) for k in kids]
        young = [(a, k) for a, k in ages if a <= max_age]
        if young:
            a, k = min(young, key=lambda x: x[0])
            return _result(pid, "met", [f"Child born {k['date']} is {a} today ({max_age} or under)."], [k] + claims)
        a, k = min(ages, key=lambda x: x[0])
        return _result(pid, "not_met", [f"Youngest documented child is {a} (born {k['date']}); the exemption covers {max_age} and under."],
                       [k], strength=0)
    if claims:
        return _result(pid, "insufficient", ["Caregiving for a child is stated, but nothing shows the child's age."], claims,
                       [_gap("CHILD_AGE_PROOF", "Need a document with the child's date of birth.", claims)], strength=0.6)
    return _result(pid, "not_met", ["No dependent child documented."], strength=0)


def ev_caregiver_disabled(ctx, pw):
    facts, case, pid = ctx["facts"], ctx["case"], pw["id"]
    claims = [f for f in _of(facts, "care_claim") if (f.get("relation") or "").lower() in ADULT_RELATIONS]
    if not claims:
        return _result(pid, "not_met", ["No caregiving for an adult documented."], strength=0)
    award = [f for f in _of(facts, "ssa_disability") if not _same_person(f.get("name"), case["member"]["name"])]
    rec = _of(facts, "care_recipient_condition")
    stated = [f for f in rec if f.get("status") == "explicit"]
    if award or stated:
        return _result(pid, "met", ["Member states regular care for a household member whose disability is documented."], claims + award + stated)
    if rec:
        conds = ", ".join(sorted({f.get("condition") for f in rec if f.get("condition")})) or "a condition"
        return _result(pid, "insufficient", [f"The care recipient's doctor letter names {conds} but does not state that it is a disability "
                                             f"or that they need help with daily activities."], claims + rec,
                       [_gap("CAREGIVER_DISABILITY_STATEMENT", "Ask the care recipient's clinician to state the disability and the help "
                                                               "needed with daily activities.", rec)], strength=0.8)
    return _result(pid, "insufficient", ["Care is described, but nothing documents the person's disability."], claims,
                   [_gap("CAREGIVER_DISABILITY_PROOF", "Need proof of the care recipient's disability (SSA award or clinician letter).", claims)],
                   strength=0.6)


def ev_member_disability_award(ctx, pw):
    mine = [f for f in _of(ctx["facts"], "ssa_disability") if _same_person(f.get("name"), ctx["case"]["member"]["name"]) or not f.get("name")]
    if mine:
        return _result(pw["id"], "met", ["Disability benefit award for the member."], mine)
    return _result(pw["id"], "not_met", ["No disability award for the member."], strength=0)


# ------------------------------------------------------------ medical frailty (interpretive)
INTERPRET_SYSTEM = """You are the interpretation agent in Coverage Keeper, a tool that helps health-plan care
coordinators and navigators keep eligible members from losing coverage over paperwork.
Program: {context}

Decide what a clinician or treatment-program letter about the MEMBER actually says, against this definition:
"{definition}" (qualifying categories: blind or disabled; substance use disorder, excluding stable recovery
of {stable}+ years; disabling mental disorder; disability that significantly impairs activities of daily
living; serious or complex medical condition).

Be strict and literal: judge only what the letter states. work_impact is "explicit" only if the letter
states the condition prevents, or significantly impairs/limits, the ability to work (or meet the
requirement). Hints such as "may have difficulty" are "vague". If it never addresses work, "absent".
impact_quote must be copied exactly from one line of the letter, or be "" if absent. All data is synthetic."""

INTERPRET_SCHEMA = {
    "type": "object",
    "properties": {
        "conditions": {"type": "array", "items": {"type": "string"}},
        "qualifying_category": {"type": "string", "enum": ["blind_or_disabled", "substance_use_disorder", "disabling_mental_disorder",
                                                           "adl_impairing_disability", "serious_or_complex", "none"]},
        "stable_recovery": {"type": "boolean"},
        "work_impact": {"type": "string", "enum": ["explicit", "vague", "absent"]},
        "impact_quote": {"type": "string"},
        "missing_statement": {"type": "string", "description": "what the letter would need to add, or ''"},
        "rationale": {"type": "string"},
    },
    "required": ["conditions", "qualifying_category", "stable_recovery", "work_impact", "impact_quote", "missing_statement", "rationale"],
    "additionalProperties": False,
}


def interpret_letters(case, facts, types, meter, use_llm, stable_years=5):
    out = []
    prog = rulebook.program()
    for d in case["documents"]:
        if types.get(d["doc_id"]) not in ("clinician_letter", "treatment_program_letter"):
            continue
        dfacts = [f for f in facts if f["doc_id"] == d["doc_id"]]
        if _of(dfacts, "care_recipient_condition") and not _of(dfacts, "diagnosis"):
            continue  # letter is about the person the member cares for, not the member
        if not _of(dfacts, "diagnosis", "work_impact"):
            continue
        res = None
        if use_llm:
            try:
                system = INTERPRET_SYSTEM.format(context=prog["domain_context"], definition=prog["frailty_definition"], stable=stable_years)
                data, _ = call_json("interpret", system, f"<letter id=\"{d['doc_id']}\">\n{d['text']}\n</letter>",
                                    INTERPRET_SCHEMA, max_tokens=4000, effort="medium", meter=meter)
                if data["impact_quote"] and not D.quote_in(d["text"], data["impact_quote"]):
                    data["rationale"] += " [impact_quote not found verbatim in letter: downgraded]"
                    data["work_impact"] = "vague" if data["work_impact"] == "explicit" else data["work_impact"]
                    data["impact_quote"] = ""
                res = dict(data, doc_id=d["doc_id"], engine="llm")
            except LLMUnavailable:
                res = None
        if res is None:
            diag = _of(dfacts, "diagnosis")
            cats = {f.get("category") for f in diag}
            rec = _of(dfacts, "recovery")
            stable = bool(rec) and max(f.get("years", 0) for f in rec) >= stable_years
            imp = [f for f in _of(dfacts, "work_impact") if f.get("status")]  # an AI reading may omit the status
            impact = imp[0]["status"] if imp else "absent"
            qual = ("serious_or_complex" if "serious_complex" in cats else "disabling_mental_disorder" if "mental" in cats
                    else "substance_use_disorder" if ("sud" in cats and not stable) else "adl_impairing_disability" if "physical" in cats
                    else "none")
            res = {"doc_id": d["doc_id"], "engine": "deterministic", "conditions": [f.get("condition") for f in diag],
                   "qualifying_category": qual, "stable_recovery": stable, "work_impact": impact,
                   "impact_quote": imp[0]["quote"] if imp and impact == "explicit" else "",
                   "missing_statement": "" if impact == "explicit" else "a statement that the condition significantly impairs the ability to work",
                   "rationale": "keyword rules"}
        res["fact_ids"] = [f["fact_id"] for f in dfacts]
        out.append(res)
    return out


def ev_clinician_interpretation(ctx, pw):
    interps, facts, pid = ctx["interps"], ctx["facts"], pw["id"]
    if not interps:
        return _result(pid, "not_met", ["No clinician letter about the member provided."], strength=0)
    ev = [f for f in facts if any(f["fact_id"] in i["fact_ids"] for i in interps)]
    qual = [i for i in interps if i["qualifying_category"] != "none"]
    explicit = [i for i in interps if i["work_impact"] == "explicit"]
    if qual and explicit:
        return _result(pid, "met", [f"Qualifying condition ({qual[0]['qualifying_category'].replace('_', ' ')}) and the letter states the "
                                    f"impact on work: \"{explicit[0]['impact_quote']}\""], ev)
    if any(i["stable_recovery"] for i in interps) and not qual:
        return _result(pid, "not_met", ["Letter documents stable recovery, which the rule excludes."], ev, strength=0)
    if qual:
        vague = any(i["work_impact"] == "vague" for i in interps)
        return _result(pid, "insufficient", [f"Letter names {', '.join(c for c in qual[0]['conditions'] if c) or 'a qualifying condition'} but "
                                             f"{'only hints at' if vague else 'does not state'} an impact on the ability to work."], ev,
                       [_gap("FRAILTY_NO_WORK_IMPACT", "The letter must state that the condition significantly impairs the member's ability "
                                                       "to meet the requirement.", ev)], strength=0.8)
    if explicit:
        return _result(pid, "insufficient", ["Letter states an impact on work but names no diagnosis."], ev,
                       [_gap("FRAILTY_NO_DIAGNOSIS", "The letter must name the diagnosis / condition.", ev)], strength=0.6)
    return _result(pid, "not_met", ["Letter does not describe a qualifying condition."], ev, strength=0)


# ------------------------------------------------------------ simple status pathways
def ev_age_scope(ctx, pw):
    age, dob = _member_age(ctx["case"], ctx["facts"])
    p = pw["params"]
    if age is not None and (age < p["min_age"] or age > p["max_age"]):
        return _result(pw["id"], "met", [f"Member is {age}; the requirement applies to ages {p['min_age']}-{p['max_age']}."], [dob])
    return _result(pw["id"], "not_met", [f"Member is {age}."], strength=0)


def ev_fact_present(ctx, pw):
    fs = _of(ctx["facts"], pw["params"]["fact_type"])
    if fs:
        return _result(pw["id"], "met", [pw["params"]["reason"]], fs)
    return _result(pw["id"], "not_met", [f"No {pw['params']['fact_type'].replace('_', ' ')} documentation."], strength=0)


def ev_pregnancy_postpartum(ctx, pw):
    facts, p, pid = ctx["facts"], pw["params"], pw["id"]
    preg, deliv = _of(facts, "pregnancy"), [f for f in _of(facts, "delivery") if f.get("date")]
    if preg:
        return _result(pid, "met", ["Clinician confirms current pregnancy."], preg)
    if not deliv:
        return _result(pid, "not_met", ["No pregnancy or recent delivery documented."], strength=0)
    f = max(deliv, key=lambda x: x["date"])
    end = add_months(date.fromisoformat(f["date"]), p["postpartum_months"])
    left = (end - config.AS_OF).days
    if left < 0:
        return _result(pid, "not_met", [f"Delivery {f['date']}; postpartum window ended {end.isoformat()}."], [f], strength=0)
    gaps = [_gap("POSTPARTUM_ENDING", f"Postpartum period (placeholder {p['postpartum_months']} months) ends {end.isoformat()}, in {left} days; "
                                      f"respond before then and plan the next pathway.", [f])] if left <= p["boundary_warning_days"] else []
    return _result(pid, "met", [f"Delivery {f['date']}; postpartum window runs to {end.isoformat()}."], [f], gaps, strength=0.7 if gaps else 1.0)


def ev_other_program_work_rule(ctx, pw):
    fs, prog = _of(ctx["facts"], pw["params"]["fact_type"]), pw["params"]["program"]
    if any(f.get("subject") for f in fs):
        return _result(pw["id"], "met", [f"{prog} notice says the member is subject to {prog} work requirements."], [f for f in fs if f.get("subject")])
    if fs:
        return _result(pw["id"], "not_met", [f"{prog} notice says the member is EXEMPT from {prog} work rules, so this does not apply."], fs, strength=0)
    return _result(pw["id"], "not_met", [f"No {prog} notice."], strength=0)


def ev_former_foster(ctx, pw):
    age, dob = _member_age(ctx["case"], ctx["facts"])
    fos = _of(ctx["facts"], "foster_care")
    if fos and age is not None and age <= pw["params"]["max_age"]:
        return _result(pw["id"], "met", [f"In foster care at 18; member is {age}."], fos + [dob])
    return _result(pw["id"], "not_met", ["No foster-care record (or member is over the age limit)."], fos, strength=0)


def ev_va_rating(ctx, pw):
    va = _of(ctx["facts"], "va_rating")
    top = max((f.get("percent", 0) for f in va), default=None)
    if top is not None and top >= pw["params"]["min_percent"]:
        return _result(pw["id"], "met", [f"VA combined rating is {top:g} percent."], va)
    return _result(pw["id"], "not_met", [f"VA rating {top:g}% (needs {pw['params']['min_percent']}%)." if top is not None else "No VA rating letter."],
                   va, strength=0)


def ev_recent_release(ctx, pw):
    first = config.AS_OF.replace(day=1)
    rel = [f for f in _of(ctx["facts"], "release") if f.get("date")]
    recent = [f for f in rel if date.fromisoformat(f["date"]) >= add_months(first, -pw["params"]["months"])]
    if recent:
        return _result(pw["id"], "met", [f"Released {recent[0]['date']}, within the {pw['params']['months']} months before {first.isoformat()}."], recent)
    return _result(pw["id"], "not_met", ["No recent release documented."], rel, strength=0)


EVALUATORS = {
    "threshold": ev_threshold, "enrollment": ev_enrollment, "combination": ev_combination,
    "clinician_interpretation": ev_clinician_interpretation, "dependent_child": ev_dependent_child,
    "caregiver_disabled": ev_caregiver_disabled, "member_disability_award": ev_member_disability_award,
    "age_scope": ev_age_scope, "fact_present": ev_fact_present, "pregnancy_postpartum": ev_pregnancy_postpartum,
    "other_program_work_rule": ev_other_program_work_rule, "former_foster": ev_former_foster, "va_rating": ev_va_rating,
    "recent_release": ev_recent_release,
}


def rank(results):
    live = [r for r in results if r["status"] != "not_met"]
    live.sort(key=lambda r: (STATUS_SCORE[r["status"]], r["strength"], KIND_SCORE[r["kind"]]), reverse=True)
    return [r["pathway"] for r in live] or ["NONE"]


def run(case, intake_out, extract_out, meter, use_llm=True):
    facts = extract_out["facts"]
    types = {d["doc_id"]: d["doc_type"] for d in intake_out["documents"]}
    frail = next((p for p in rulebook.pathways() if p["evaluator"] == "clinician_interpretation"), None)
    interps = interpret_letters(case, facts, types, meter, use_llm, frail["params"].get("stable_recovery_years", 5)) if frail else []
    ctx = {"case": case, "facts": facts, "interps": interps}
    results = [EVALUATORS[pw["evaluator"]](ctx, pw) for pw in rulebook.pathways()]
    engine = "llm+deterministic" if any(i["engine"] == "llm" for i in interps) else "deterministic"
    return {"pathways": results, "ranking": rank(results), "interpretations": interps}, engine, None
