"""Stage 2 - Extraction: structured facts, each tied to a document line and an exact quote.

Two engines produce the same fact format:
  llm           - Claude reads the line-numbered documents and returns facts with quotes
  deterministic - pattern rules (a baseline; tuned on the dev split's document styles)
Every fact is grounded afterwards: if its quote is not literally in the document it is dropped.
"""
import re

from .. import config, rulebook
from .. import docs as D
from ..llm import LLMUnavailable, call_json
from .intake import classify_rules
from ..textutil import add_months, age_on, find_dates, find_month, first_date, guess_language, money

FACT_TYPES = [
    "work_hours", "earnings", "enrollment", "medicare", "member_dob", "pregnancy", "delivery", "child",
    "care_claim", "ssa_disability", "diagnosis", "work_impact", "recovery", "sud_treatment", "snap", "tafdc",
    "va_rating", "foster_care", "release", "tribal", "doc_language", "care_recipient_condition",
]

FACT_DESC = {
    "work_hours": "hours of work, community service or a work program",
    "earnings": "money earned",
    "enrollment": "school enrollment status and credits",
    "medicare": "the member is enrolled in Medicare",
    "member_dob": "the member's date of birth",
    "pregnancy": "the member is pregnant (date = due date)",
    "delivery": "the member gave birth (date = delivery date)",
    "child": "a child of the member, with the child's date of birth",
    "care_claim": "the MEMBER says they care for, help or live with someone (child or adult); one fact per statement, "
                  "even if it also mentions that person's condition",
    "ssa_disability": "a Social Security disability benefit award (name = beneficiary)",
    "diagnosis": "a diagnosis of the MEMBER in a clinician or treatment-program letter",
    "work_impact": "what a clinician letter about the member says about the ability to work",
    "recovery": "time in remission or recovery",
    "sud_treatment": "the member currently takes part in a substance-use treatment program",
    "snap": "SNAP notice: whether the member is subject to its work requirement",
    "tafdc": "TAFDC notice: whether the member is subject to its work requirement",
    "va_rating": "VA disability rating",
    "foster_care": "the member was in foster care at 18",
    "release": "release from incarceration (date = release date)",
    "tribal": "the member is an enrolled tribal member",
    "doc_language": "the language of a non-English document",
    "care_recipient_condition": "a CLINICIAN letter's statement about the condition of someone other than the member",
}

FIELDS = {
    "month": "YYYY-MM the activity/earnings belong to, or null if ongoing/unspecified",
    "hours": "hours in that month (for weekly figures give the weekly number and set basis=weekly)",
    "activity": "work | community_service | work_program (for work_hours)",
    "amount": "dollar amount (earnings)",
    "basis": "monthly | per_period | weekly | estimate",
    "status": "enrollment: full_time | half_time | less_than_half | part_time_unspecified | unspecified; "
              "work_impact: explicit | vague | absent",
    "credits": "credit hours (enrollment)",
    "date": "YYYY-MM-DD: due date, delivery date, child DOB, member DOB, release date, start date",
    "name": "person the fact is about when it is not the member (child, care recipient, SSA beneficiary)",
    "relation": "relationship of that person to the member (son, mother, brother, ...)",
    "lives_with": "true if the member lives with the child / care recipient",
    "condition": "diagnosis name (diagnosis) or program name (sud_treatment)",
    "category": "diagnosis: physical | mental | sud | developmental | serious_complex",
    "care_recipient_condition": "use this type (not diagnosis) when a clinician letter is about someone OTHER than the member; "
                                "status explicit ONLY if the letter itself says the person is disabled / has a disability or "
                                "needs help with daily activities; a diagnosis, symptom or impairment alone (e.g. 'weakness') "
                                "is absent",
    "percent": "VA combined rating percent",
    "subject": "snap/tafdc: true if member is SUBJECT TO (not exempt from) the work requirement",
    "part": "medicare: A, B or AB",
    "years": "recovery: years in remission",
    "language": "doc_language: ISO 639-1",
}


def _fact(ftype, doc, line_no, **kw):
    lines = doc["text"].splitlines()
    return {"type": ftype, "doc_id": doc["doc_id"], "line": line_no,
            "quote": lines[line_no - 1].strip() if 0 < line_no <= len(lines) else "", **kw}


# ------------------------------------------------------------------ deterministic engine
RE_HOURS = re.compile(r"(\d+(?:\.\d+)?)\s*(?:hours|horas|hrs)\b", re.I)
RE_HOURS_AFTER = re.compile(r"h\w{3,4}s?\s+worked:\s*(\d+(?:\.\d+)?)", re.I)
RE_NUM_AFTER_COLON = re.compile(r"(?:total hours|hours)\s*:\s*(\d+(?:\.\d+)?)", re.I)

CONDITIONS = [
    (r"pulmonary fibrosis|copd|obstructive pulmonary", "serious_complex"),
    (r"heart failure", "serious_complex"),
    (r"cancer|chemotherapy", "serious_complex"),
    (r"rheumatoid arthritis|artritis reumatoide", "physical"),
    (r"major depressive|depression|ptsd|post-traumatic|bipolar|schizo", "mental"),
    (r"opioid use disorder|alcohol use disorder|substance use disorder", "sud"),
    (r"hypertension", "physical"),
    (r"ischemic stroke|stroke|hemiparesis|accidente cerebrovascular", "serious_complex"),
    (r"type 2 diabetes|diabetes", "physical"),
]
EXPLICIT_IMPACT = [
    r"unable to work", r"not able to work", r"cannot work", r"prevents? (?:him|her|them)? ?from (?:maintaining )?(?:employment|work)",
    r"significantly (?:impairs|limits?) (?:his|her|their) ability to (?:work|meet|comply)",
    r"significantly limit (?:his|her|their) ability to work", r"impide trabajar", r"incapaz de trabajar",
    r"unable to (?:sustain|maintain) employment", r"prevent (?:her|him|them) from maintaining employment",
]
DISABILITY_STATED = (r"is disabled|has a disability|substantially limits|requires (?:daily )?assistance with|needs help with "
                     r"(?:bathing|dressing|daily)|unable to (?:bathe|dress|walk|care for)")


ES_RELATION = {"madre": "mother", "mamá": "mother", "padre": "father", "hijo": "son", "hija": "daughter", "hermano": "brother",
               "hermana": "sister", "esposo": "husband", "esposa": "wife", "abuela": "grandmother", "abuelo": "grandfather"}


def _patient(lines):
    for l in lines[:12]:
        m = re.match(r"\s*(?:re|patient|paciente)\s*:\s*(.+?)(?:\s{2,}|\s+dob|\s+fecha|$)", l, re.I)
        if m:
            return m.group(1).strip()
    return None


def _same_first(a, b):
    ta, tb = (a or "").lower().split(), (b or "").lower().split()
    return bool(ta and tb and ta[0] == tb[0])


VAGUE_IMPACT = [r"may have difficulty", r"would benefit", r"some difficulty", r"limitations? at times"]


def _activity_for(dtype):
    return {"volunteer_record": "community_service", "job_training_record": "work_program"}.get(dtype, "work")


def _doc_month(text):
    for line in text.splitlines()[:8]:
        m = find_month(line)
        if m and not re.search(r"date:|dob|birth|letter", line, re.I):
            return m
    return None


def extract_rules(doc, dtype, member):
    text, lines, facts = doc["text"], doc["text"].splitlines(), []
    low = text.lower()
    lang = guess_language(text)
    if lang != "en":
        facts.append(_fact("doc_language", doc, 1, language=lang))

    if dtype == "pay_stub":
        period_end = None
        for i, line in enumerate(lines, 1):
            if re.search(r"pay period", line, re.I):
                ds = find_dates(line)
                period_end = ds[-1] if ds else None
            m = RE_HOURS_AFTER.search(line)
            if m and period_end:
                facts.append(_fact("work_hours", doc, i, month=f"{period_end:%Y-%m}", hours=float(m.group(1)),
                                   activity="work", basis="per_period"))
            if re.match(r"\s*gross pay", line, re.I) and period_end:
                facts.append(_fact("earnings", doc, i, month=f"{period_end:%Y-%m}", amount=money(line), basis="per_period"))

    elif dtype == "gig_earnings_statement":
        stmt_month = None
        for i, line in enumerate(lines, 1):
            if re.search(r"statement month", line, re.I):
                stmt_month = find_month(line)
            if re.search(r"week of", line, re.I) and money(line) is not None:
                d = first_date(line)
                if d:
                    facts.append(_fact("earnings", doc, i, month=f"{d:%Y-%m}", amount=money(line), basis="per_period"))
            elif re.search(r"total earnings", line, re.I) and money(line) is not None:
                facts.append(_fact("earnings", doc, i, month=stmt_month, amount=money(line), basis="monthly"))

    elif dtype in ("employer_letter", "volunteer_record", "job_training_record"):
        dm = _doc_month(text)
        for i, line in enumerate(lines, 1):
            if re.search(r"per week|a week|por semana", line, re.I):
                m = RE_HOURS.search(line)
                if m:
                    facts.append(_fact("work_hours", doc, i, month=None, hours=float(m.group(1)),
                                       activity=_activity_for(dtype), basis="weekly"))
                    rate = money(line)
                    if rate and re.search(r"per hour|/hr|an hour", line, re.I):
                        facts.append(_fact("earnings", doc, i, month=None, amount=round(rate * float(m.group(1)) * 4.33, 2),
                                           basis="estimate"))
                continue
            m = RE_NUM_AFTER_COLON.search(line) or RE_HOURS.search(line)
            if m and not re.search(r"each day|per day|a day", line, re.I):
                month = find_month(line) or dm
                facts.append(_fact("work_hours", doc, i, month=month, hours=float(m.group(1)),
                                   activity=_activity_for(dtype), basis="monthly"))

    elif dtype == "school_enrollment_letter":
        status, credits, sline, cline = "unspecified", None, None, None
        for i, line in enumerate(lines, 1):
            l = line.lower()
            for pat, st in [(r"less than half[- ]time", "less_than_half"), (r"full[- ]time", "full_time"),
                            (r"half[- ]time", "half_time"), (r"part[- ]time", "part_time_unspecified")]:
                if re.search(pat, l) and sline is None:
                    status, sline = st, i
                    break
            c = re.search(r"(\d+)\s*credit", l) or re.search(r"credit hours?\s*:\s*(\d+)", l)
            if c:
                credits, cline = int(c.group(1)), cline or i
        sline = sline or cline
        if sline is None:
            sline = next((i for i, l in enumerate(lines, 1) if re.search(r"enrolled|registered", l, re.I)), 1)
        facts.append(_fact("enrollment", doc, sline, status=status, credits=credits))

    elif dtype == "medicare_card":
        for i, line in enumerate(lines, 1):
            a, b = bool(re.search(r"part a", line, re.I)), bool(re.search(r"part b", line, re.I))
            if a or b:
                facts.append(_fact("medicare", doc, i, part=("A" if a else "") + ("B" if b else "")))

    elif dtype == "id_card":
        for i, line in enumerate(lines, 1):
            if re.search(r"\bdob\b|date of birth", line, re.I) and first_date(line):
                facts.append(_fact("member_dob", doc, i, date=first_date(line).isoformat()))

    elif dtype == "hospital_discharge_or_prenatal":
        for i, line in enumerate(lines, 1):
            l = line.lower()
            if re.search(r"due date", l) and first_date(line):
                facts.append(_fact("pregnancy", doc, i, date=first_date(line).isoformat()))
            elif re.search(r"currently pregnant", l):
                facts.append(_fact("pregnancy", doc, i, date=None))
            elif re.search(r"date of delivery|delivered", l) and first_date(line):
                facts.append(_fact("delivery", doc, i, date=first_date(line).isoformat(),
                                   lives_with=("stillbirth" not in low)))

    elif dtype == "birth_record":
        name, nline = None, None
        for i, line in enumerate(lines, 1):
            m = re.match(r"\s*(?:child's name|name of child|child)\s*:\s*(.+)", line, re.I)
            if m:
                name, nline = m.group(1).strip(), i
            if re.search(r"date of birth", line, re.I) and first_date(line):
                facts.append(_fact("child", doc, i, name=name, date=first_date(line).isoformat(), relation="child"))

    elif dtype == "caregiver_attestation":
        for i, line in enumerate(lines, 1):
            l = line.lower()
            m = re.search(r"\b(?:my|her|his)\s+(son|daughter|child|mother|father|brother|sister|husband|wife|grandmother|grandfather)\b", l)
            if m and re.search(r"live|take care|caregiver|help", l):
                facts.append(_fact("care_claim", doc, i, relation=m.group(1), lives_with=bool(re.search(r"\blive", l)),
                                   name=None))
                break
            es = re.search(r"\bmi\s+(madre|mamá|padre|hijo|hija|hermano|hermana|esposo|esposa|abuela|abuelo)\b", l)
            if es and re.search(r"vivo|cuido|ayudo|cuidador", l):
                facts.append(_fact("care_claim", doc, i, relation=ES_RELATION[es.group(1)], lives_with=bool(re.search(r"\bvivo", l)),
                                   name=None))
                break

    elif dtype == "ssa_disability_letter":
        ben = next((re.sub(r"^.*?:\s*", "", l).strip() for l in lines if re.search(r"beneficiary", l, re.I)), None)
        for i, line in enumerate(lines, 1):
            if re.search(r"became disabled|disability benefits", line, re.I):
                facts.append(_fact("ssa_disability", doc, i, name=ben))
                break

    elif dtype == "clinician_letter" and _patient(lines) and not _same_first(_patient(lines), member.get("name")):
        who = _patient(lines)
        for i, line in enumerate(lines, 1):
            for pat, cat in CONDITIONS:
                m = re.search(pat, line.lower())
                if m:
                    facts.append(_fact("care_recipient_condition", doc, i, name=who, condition=m.group(0), status="absent"))
        stated = next((i for i, l in enumerate(lines, 1) if re.search(DISABILITY_STATED, l.lower())), None)
        if stated:
            facts.append(_fact("care_recipient_condition", doc, stated, name=who, status="explicit"))
            for f in facts:
                if f["type"] == "care_recipient_condition":
                    f["status"] = "explicit"

    elif dtype in ("clinician_letter", "treatment_program_letter"):
        for i, line in enumerate(lines, 1):
            l = line.lower()
            for pat, cat in CONDITIONS:
                m = re.search(pat, l)
                if m:
                    facts.append(_fact("diagnosis", doc, i, condition=m.group(0), category=cat))
            m = re.search(r"(?:remission|recovery) since (\d{4})", l)
            if m:
                facts.append(_fact("recovery", doc, i, years=config.AS_OF.year - int(m.group(1))))
            if re.search(r"early (?:remission|recovery)", l):
                facts.append(_fact("recovery", doc, i, years=0))
            if dtype == "treatment_program_letter" and re.search(r"enrolled in|participating in", l):
                facts.append(_fact("sud_treatment", doc, i, condition="treatment program"))
        impact_line = next((i for i, l in enumerate(lines, 1) if any(re.search(p, l.lower()) for p in EXPLICIT_IMPACT)), None)
        if impact_line:
            facts.append(_fact("work_impact", doc, impact_line, status="explicit"))
        elif dtype == "clinician_letter" and any(f["type"] == "diagnosis" for f in facts):
            vague = next((i for i, l in enumerate(lines, 1) if any(re.search(p, l.lower()) for p in VAGUE_IMPACT)), None)
            facts.append(_fact("work_impact", doc, vague or 1, status="vague" if vague else "absent"))

    elif dtype == "snap_notice":
        for i, line in enumerate(lines, 1):
            l = line.lower()
            if re.search(r"exempt from snap work", l):
                facts.append(_fact("snap", doc, i, subject=False))
            elif re.search(r"subject to snap work|must meet", l):
                facts.append(_fact("snap", doc, i, subject=True))
                break

    elif dtype == "va_rating_letter":
        for i, line in enumerate(lines, 1):
            m = re.search(r"(\d{1,3})\s*(?:percent|%)", line, re.I)
            if m:
                facts.append(_fact("va_rating", doc, i, percent=int(m.group(1))))

    elif dtype == "foster_care_letter":
        for i, line in enumerate(lines, 1):
            if re.search(r"foster care", line, re.I):
                facts.append(_fact("foster_care", doc, i))
            if re.search(r"\bdob\b", line, re.I) and first_date(line):
                facts.append(_fact("member_dob", doc, i, date=first_date(line).isoformat()))

    elif dtype == "release_paperwork":
        for i, line in enumerate(lines, 1):
            if re.search(r"release", line, re.I) and first_date(line):
                facts.append(_fact("release", doc, i, date=first_date(line).isoformat()))

    elif dtype == "tribal_enrollment":
        for i, line in enumerate(lines, 1):
            if re.search(r"enrolled member|tribal member", line, re.I):
                facts.append(_fact("tribal", doc, i))
    return facts


# ------------------------------------------------------------------ LLM engine
SYSTEM = """You are the extraction agent in Coverage Keeper, which helps health-plan care coordinators and navigators
keep eligible members from losing coverage over paperwork. Program: {context}
All data is synthetic.

Extract every fact relevant to: work/volunteer/job-training hours, earnings, school enrollment status,
Medicare enrollment, date of birth, pregnancy/delivery, dependent children and their birth dates,
caregiving for a person with a disability, SSA disability awards, diagnoses, whether a clinician letter
states the condition affects the ability to work, recovery length, substance-use treatment program
participation, SNAP/TAFDC work-requirement status, VA disability rating, foster care at 18, release from
incarceration, tribal enrollment, and the language of any non-English document.

Rules:
- "quote" must be copied EXACTLY, character for character, from ONE line of the document (no line-number prefix).
- "line" is the 1-based line number shown before the "|".
- Use null for any field that does not apply. Never infer values not written in the document.
- For each pay stub period, emit one work_hours and one earnings fact (basis=per_period, month=month of the period end).
- For weekly payouts emit one earnings fact per week (month = month of that week's date).
- For work_impact: "explicit" only if the letter states the condition prevents, or significantly impairs/limits,
  the ability to work or meet a work requirement; "vague" if it only hints (e.g. 'may have difficulty');
  "absent" if it never addresses work. Emit one work_impact fact per clinician letter that names a diagnosis.
- Enrollment status must be what the school states; 'part-time' without 'half-time' is part_time_unspecified.
- A member's own statement that they care for someone is a care_claim, never a care_recipient_condition.
- Give relation in English (mother, son, ...) whatever the document's language.

Fact types: """ + "; ".join(f"{k}: {v}" for k, v in FACT_DESC.items()) + """

Fields: """ + "; ".join(f"{k}: {v}" for k, v in FIELDS.items())

_nullable = lambda t: {"type": [t, "null"]}
SCHEMA = {
    "type": "object",
    "properties": {"facts": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "type": {"type": "string", "enum": FACT_TYPES},
            "doc_id": {"type": "string"},
            "line": {"type": "integer"},
            "quote": {"type": "string"},
            "month": _nullable("string"), "hours": _nullable("number"), "activity": _nullable("string"),
            "amount": _nullable("number"), "basis": _nullable("string"), "status": _nullable("string"),
            "credits": _nullable("number"), "date": _nullable("string"), "name": _nullable("string"),
            "relation": _nullable("string"), "lives_with": _nullable("boolean"), "condition": _nullable("string"),
            "category": _nullable("string"), "percent": _nullable("number"), "subject": _nullable("boolean"),
            "part": _nullable("string"), "years": _nullable("number"), "language": _nullable("string"),
        },
        "required": ["type", "doc_id", "line", "quote", "month", "hours", "activity", "amount", "basis", "status",
                     "credits", "date", "name", "relation", "lives_with", "condition", "category", "percent",
                     "subject", "part", "years", "language"],
        "additionalProperties": False}}},
    "required": ["facts"], "additionalProperties": False,
}


def _ground(facts, docs_by_id):
    """Keep only facts whose quote is literally in the cited document; fix line numbers."""
    kept, dropped = [], []
    for f in facts:
        doc = docs_by_id.get(f.get("doc_id"))
        if doc and D.quote_in(doc["text"], f.get("quote", "")):
            f["line"] = D.find_line(doc["text"], f["quote"]) or f.get("line")
            kept.append(f)
        else:
            dropped.append(f)
    return kept, dropped


# ------------------------------------------------------------------ cross-check: the LLM must not miss what the rules find
# Fact types whose value is a judgement (the LLM's reading is preferred when it gives one): coverage is per document.
INTERPRETIVE = {"work_impact", "care_recipient_condition", "recovery", "doc_language", "diagnosis"}
_VALUE_KEYS = ("hours", "amount", "date", "status", "percent", "part", "credits", "relation")


def _value(f):
    v = next((f.get(k) for k in _VALUE_KEYS if f.get(k) not in (None, "")), None)
    return f"{float(v):g}" if isinstance(v, (int, float)) and not isinstance(v, bool) else str(v).lower() if v is not None else None


def _uncovered(facts, reference, hard_only=False):
    """Facts in `reference` (the rules engine's) that `facts` (the LLM's) do not cover: same document and type, and the
    same line or the same value. hard_only limits this to plain facts the rules read reliably (hours, money, dates)."""
    out = []
    for r in reference:
        if hard_only and r["type"] in INTERPRETIVE:
            continue
        same = [f for f in facts if f["doc_id"] == r["doc_id"] and f["type"] == r["type"]]
        if r["type"] in INTERPRETIVE:
            # A judgement the AI gave counts; one it left without its status (e.g. work impact) does not.
            hit = any(f.get("status") or not r.get("status") for f in same)
        else:
            hit = any(f.get("line") == r.get("line") or (_value(f) is not None and _value(f) == _value(r)) for f in same)
        if not hit:
            out.append(r)
    return out


def run(case, intake_out, meter, use_llm=True):
    types = {d["doc_id"]: d["doc_type"] for d in intake_out["documents"]}
    docs_by_id = {d["doc_id"]: d for d in case["documents"]}
    facts, engine, note = None, "deterministic", None
    if use_llm:
        # The rules engine reads the same documents in milliseconds, classifying them itself so an LLM intake slip
        # can't mislead it. Its plain facts (hours, earnings, birth dates...) are a floor the LLM reading must reach.
        reference = []
        for d in case["documents"]:
            reference.extend(extract_rules(d, classify_rules(d), case["member"]))
        reference, _ = _ground(reference, docs_by_id)
        clean = lambda data: _ground([{k: v for k, v in f.items() if v is not None} for f in data["facts"]], docs_by_id)[0]
        user = (f"Member basics (from navigator intake): age {case['member'].get('age')}, "
                f"household: {case['member'].get('household', '')}\n\n" +
                "\n\n".join(f"<document id=\"{d['doc_id']}\" type=\"{types[d['doc_id']]}\">\n{D.numbered(d['text'])}\n</document>"
                            for d in case["documents"]))
        try:
            data, info = call_json("extract", SYSTEM.replace("{context}", rulebook.program()["domain_context"]), user, SCHEMA, meter=meter,
                                   accept=lambda d: not _uncovered(clean(d), reference, hard_only=True))
            facts = [{k: v for k, v in f.items() if v is not None} for f in data["facts"]]
            engine = "llm"
            missed = _uncovered(_ground([dict(f) for f in facts], docs_by_id)[0], reference)
            if missed:
                facts += [dict(r) for r in missed]
                engine = "llm+rules"
                what = ", ".join(sorted({f"{r['type'].replace('_', ' ')} in {r['doc_id']}" for r in missed}))
                again = "" if info.get("accepted", True) else " (in a saved reply)" if info.get("cached") else " even after asking again"
                note = f"The AI reading missed {len(missed)} fact(s) the rules found ({what}){again}; added them from the rules."
        except LLMUnavailable as e:
            note = str(e)
    if facts is None:
        facts = []
        for d in case["documents"]:
            facts.extend(extract_rules(d, types[d["doc_id"]], case["member"]))
    facts, dropped = _ground(facts, docs_by_id)
    for i, f in enumerate(facts, 1):
        f["fact_id"] = f"F{i}"
    return {"facts": facts, "ungrounded_dropped": dropped}, engine, note


__all__ = ["run", "FACT_TYPES", "add_months", "age_on"]
