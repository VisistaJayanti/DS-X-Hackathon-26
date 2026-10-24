"""Stage 5 - Drafting: response packet, request letter to a clinician/school/employer, member explanation.

Every non-boilerplate sentence is a *claim* carrying its support, so the verifier can check it:
  fact     - doc_id + exact quote from that document
  finding  - rule_id + the fact_ids it rests on (a conclusion computed by the rules stage)
  rule     - rule_id (quotes or paraphrases the rulebook)
  request  - something we are asking a third party to provide (asserts nothing about the member)
"""
from .. import config, i18n, rulebook
from ..llm import LLMUnavailable, call_json

def DOC_LABEL():
    return rulebook.active()["doc_labels"]


def REQUESTS():
    return {code: g["requests"] for code, g in rulebook.active()["gap_codes"].items() if g.get("requests")}


ASK_TITLE = {"clinician": "Request for an updated clinician letter", "school": "Request for enrollment verification",
             "employer": "Request for a statement of hours"}


def _claim(cid, kind, text, **kw):
    return {"claim_id": cid, "kind": kind, "text": text, **kw}


def _first(case):
    return case["member"]["name"].split()[0]


def deterministic(case, intake_out, extract_out, rules_out, gaps_out):
    facts = {f["fact_id"]: f for f in extract_out["facts"]}
    types = {d["doc_id"]: d["doc_type"] for d in intake_out["documents"]}
    paths = {p["pathway"]: p for p in rules_out["pathways"]}
    ranking, dl = rules_out["ranking"], gaps_out["deadline"]
    n = [0]

    def nid(prefix):
        n[0] += 1
        return f"{prefix}{n[0]}"

    def shown(f):
        return f["type"] != "doc_language" and not (f["type"] == "work_impact" and f.get("status") != "explicit")

    def fact_claim(prefix, f):
        return _claim(nid(prefix), "fact", f"{DOC_LABEL().get(types.get(f['doc_id']), 'Document')} ({f['doc_id']}, line {f['line']}) states: "
                                          f"“{f['quote']}”", doc_id=f["doc_id"], quote=f["quote"])

    # ---------------- packet
    packet = {"status": "none", "sections": []}
    lead = [p for p in ranking if p != "NONE"]
    support = [paths[p] for p in lead if paths[p]["status"] == "met"][:2] or [paths[p] for p in lead[:1]]
    if support:
        packet["status"] = "ready" if gaps_out["evidence_sufficient"] else "hold"
        for p in support:
            r = rulebook.rules()[p["rule_id"]]
            sec = {"heading": p["name"], "claims": [
                _claim(nid("P"), "rule", f"Basis: {r['name']} ({r['cite']}).", rule_id=r["id"]),
                _claim(nid("P"), "rule", f"Rule text: “{r['quote']}”", rule_id=r["id"]),
            ]}
            sec["claims"] += [fact_claim("P", facts[e]) for e in p["evidence"] if e in facts and shown(facts[e])]
            sec["claims"] += [_claim(nid("P"), "finding", f"Summary: {reason}", rule_id=r["id"], fact_ids=p["evidence"])
                              for reason in p["reasons"]]
            packet["sections"].append(sec)
        enc = sorted({facts[e]["doc_id"] for p in support for e in p["evidence"] if e in facts})
        packet["enclosures"] = [f"{d}: {DOC_LABEL().get(types.get(d), 'Document')}" for d in enc]

    # ---------------- request letter to a third party
    request = None
    g = next((g for g in gaps_out["gaps"] if g["code"] in REQUESTS()), None)
    if g:
        p = paths[g["pathway"]]
        r = rulebook.rules()[p["rule_id"]]
        ev = [facts[e] for e in g["evidence"] if e in facts and shown(facts[e])][:3]
        claims = [fact_claim("Q", f) for f in ev]
        claims.append(_claim(nid("Q"), "rule", f"The federal rule ({r['cite']}) reads: “{r['quote']}”", rule_id=r["id"]))
        recipient = next((f.get("name") for f in ev if f.get("name")), "the person you care for")
        claims += [_claim(nid("Q"), "request", s.format(first=_first(case), recipient=recipient)) for s in REQUESTS()[g["code"]]]
        if dl:
            ask_by = dl["ask_third_party_by"]
            claims.append(_claim(nid("Q"), "request", f"Please reply by {ask_by} so the member can meet the {rulebook.program()['agency']} deadline of {dl['due']}.",
                                 rule_id=dl["rule_id"]))
        request = {"to": g["ask"], "title": ASK_TITLE.get(g["ask"], "Request for documentation"), "gap": g["code"], "claims": claims}

    # ---------------- member explanation (English master; translated in a separate step)
    member = [{"key": "intro", "kw": {"first": _first(case)}}]
    top = ranking[0]
    if top == "NONE":
        member.append({"key": "none", "kw": {}})
    else:
        member.append({"key": "out_of_scope" if top.startswith("OUT_OF_SCOPE") else "likely", "kw": {"pathway": top},
                       "rule_id": paths[top]["rule_id"], "fact_ids": paths[top]["evidence"]})
    member_gaps = [g["code"] for g in gaps_out["gaps"]]
    if member_gaps:
        member.append({"key": "need_intro", "kw": {}})
        member += [{"key": "gap", "kw": {"code": c}} for c in member_gaps]
    elif top != "NONE":
        member.append({"key": "ready", "kw": {}})
    if dl:
        member.append({"key": "overdue" if dl["days_left"] < 0 else "deadline", "kw": {"date": dl["due"], "days": dl["days_left"]},
                       "rule_id": dl["rule_id"]})
    member.append({"key": "decides", "kw": {}})
    english = [_claim(f"M{i + 1}", "finding" if s.get("rule_id") else "boilerplate", render(s, "en"), rule_id=s.get("rule_id"),
                      fact_ids=s.get("fact_ids", []), template=s) for i, s in enumerate(member)]
    return {"packet": packet, "request": request, "member_en": english}


def render(s, lang):
    if s["key"] == "gap":
        return "• " + i18n.gap_text(s["kw"]["code"], lang)
    if s["key"] == "option":
        return f"• {s['kw']['name']}: {s['kw']['contact']}"
    kw = dict(s["kw"])
    if "pathway" in kw:
        kw["pathway"] = i18n.pathway_name(kw["pathway"], lang)
    if "trigger" in kw:
        lab = rulebook.active()["transitions"]["triggers"][kw["trigger"]]["label"]
        kw["trigger"] = lab.get(lang, lab["en"])
    if "submit" in kw:
        sub = rulebook.active()["reconsideration"]["submit"]
        kw["submit"] = sub.get(lang, sub["en"])
    return i18n.t(s["key"], lang, **kw)


def frame(case, draft_out, outcome_out):
    """Re-frame drafts for Recover / Transition. Retain drafts are returned unchanged."""
    oc = (outcome_out or {}).get("outcome", "retain")
    if oc == "retain":
        return dict(draft_out, outcome="retain")
    first = _first(case)
    old = [c["template"] for c in draft_out["member_en"] if c.get("template")]
    keep = [s for s in old if s["key"] in ("likely", "out_of_scope", "need_intro", "gap", "ready")]
    member = [{"key": "intro", "kw": {"first": first}}]
    packet, request, plan = draft_out["packet"], draft_out["request"], None

    if oc == "recover":
        rc = outcome_out["reconsideration"]
        r = rulebook.rules()[rc["rule_id"]]
        head = {"heading": "Reconsideration submission", "claims": [
            _claim("R1", "rule", f"Basis: {r['name']} ({r['cite']}).", rule_id=r["id"]),
            _claim("R2", "rule", f"Rule text: “{r['quote']}”", rule_id=r["id"]),
            _claim("R3", "finding", f"Coverage ended on {rc['termination_date']} for missing paperwork; this submission is sent within the "
                                    f"{rc['window_days']}-day reconsideration period, which ends {rc['ends']}.", rule_id=r["id"]),
        ]}
        packet = dict(packet, sections=[head] + packet["sections"], status=packet["status"] if packet["sections"] else "hold")
        member += [{"key": "recover_intro", "kw": {"term": rc["termination_date"]}, "rule_id": rc["rule_id"]},
                   {"key": "recover_window", "kw": {"submit": True, "date": rc["ends"], "days": rc["days_left"]}, "rule_id": rc["rule_id"]}]
        member += keep + [{"key": "recover_no_promise", "kw": {}}]
        if request:
            ask = rc["ask_third_party_by"]
            request = dict(request, claims=[dict(c, text=f"Please reply by {ask} so the member can send it within the reconsideration "
                                                          f"period ending {rc['ends']}.", rule_id=rc["rule_id"])
                                            if c["text"].startswith("Please reply by") else c for c in request["claims"]])
    elif oc == "recover_expired":
        rc = outcome_out["reconsideration"]
        packet = dict(packet, sections=[dict(s, heading="Documents for a new application: " + s["heading"]) for s in packet["sections"]])
        member += [{"key": "recover_intro", "kw": {"term": rc["termination_date"]}, "rule_id": rc["rule_id"]},
                   {"key": "recover_expired", "kw": {"date": rc["ends"]}, "rule_id": rc["rule_id"]}] + keep
    t = outcome_out.get("transition")
    if oc == "transition":
        packet, request = {"status": "none", "sections": []}, None
    if t and oc in ("transition", "recover_expired"):
        w = t["window"] or {}
        member += [{"key": "transition_intro", "kw": {"trigger": t["trigger"]}, "rule_id": t["trigger_rule_id"]},
                   {"key": "transition_options", "kw": {}}]
        member += [{"key": "option", "kw": {"name": o["name"], "contact": o["contact"]}} for o in t["options"]]
        if w:
            member.append({"key": "transition_deadline", "kw": {"avoid": w["avoid_gap_by"], "closes": w["closes"]}, "rule_id": w["rule_id"]})
        member += [{"key": "transition_docs", "kw": {"docs": "; ".join(d[0].lower() + d[1:] if not d.split()[0].isupper() and d.split()[0] != "Photo" else d for d in t["documents"])}},
                   {"key": "transition_wrong", "kw": {}}]
        plan = t
    member.append({"key": "decides", "kw": {}})
    english = [_claim(f"M{i + 1}", "finding" if s.get("rule_id") else "boilerplate", render(s, "en"), rule_id=s.get("rule_id"),
                      fact_ids=s.get("fact_ids", []), template=s) for i, s in enumerate(member)]
    return {"packet": packet, "request": request, "member_en": english, "transition_plan": plan, "outcome": oc}


# ------------------------------------------------------------------ LLM drafter
SYSTEM = """You are the drafting agent in Coverage Keeper, which helps health-plan care coordinators and navigators keep
eligible members from losing coverage over paperwork. Program: {context}
The agency that decides is {agency}. All data is synthetic.

Write three things as lists of short claims (one sentence each):
1. packet: a cover letter to the agency listing the evidence for the leading pathway(s).
2. request: if a gap needs a clinician, school or employer, a letter to them asking for exactly what is missing.
3. member: a warm, plain-language explanation for the member (6th-grade reading level, English).

Every claim must carry its support:
- kind "fact": doc_id and a quote copied EXACTLY from that document.
- kind "finding": rule_id and the fact_ids it rests on.
- kind "rule": rule_id.
- kind "request": something you are asking the recipient to provide.
Never state that the member IS eligible, exempt, or approved: the agency decides. Use "the documents
support", "likely pathway", "may qualify". Do not mention anything that is not in the provided facts,
pathway results, gaps, or rules."""

_claim_schema = {"type": "object", "properties": {
    "kind": {"type": "string", "enum": ["fact", "finding", "rule", "request"]},
    "text": {"type": "string"}, "doc_id": {"type": ["string", "null"]}, "quote": {"type": ["string", "null"]},
    "rule_id": {"type": ["string", "null"]}, "fact_ids": {"type": "array", "items": {"type": "string"}}},
    "required": ["kind", "text", "doc_id", "quote", "rule_id", "fact_ids"], "additionalProperties": False}
SCHEMA = {"type": "object", "properties": {
    "packet": {"type": "array", "items": _claim_schema},
    "request_to": {"type": ["string", "null"], "enum": ["clinician", "school", "employer", None]},
    "request": {"type": "array", "items": _claim_schema},
    "member": {"type": "array", "items": _claim_schema}},
    "required": ["packet", "request_to", "request", "member"], "additionalProperties": False}


def llm(case, intake_out, extract_out, rules_out, gaps_out, meter):
    import json

    rb = rulebook.rules()
    paths = [p for p in rules_out["pathways"] if p["status"] != "not_met"]
    prog = rulebook.program()
    used_rules = {p["rule_id"] for p in paths} | {prog["deadline_rule"]}
    ctx = {
        "member": {k: case["member"].get(k) for k in ("name", "age", "household", "notice_type")},
        "deadline": gaps_out["deadline"],
        "documents": [{"doc_id": d["doc_id"], "type": d["doc_type"]} for d in intake_out["documents"]],
        "facts": extract_out["facts"],
        "ranking": rules_out["ranking"],
        "pathways": paths,
        "gaps": gaps_out["gaps"],
        "rules": {rid: {k: rb[rid][k] for k in ("name", "cite", "quote")} for rid in used_rules},
    }
    data, _ = call_json("draft", SYSTEM.format(context=prog["domain_context"], agency=prog["agency"]), json.dumps(ctx, ensure_ascii=False, indent=1), SCHEMA, meter=meter)
    norm = lambda c, pre, i: dict({k: v for k, v in c.items() if v not in (None, [])}, claim_id=f"{pre}{i + 1}")
    packet_claims = [norm(c, "P", i) for i, c in enumerate(data["packet"])]
    lead = rules_out["ranking"][0]
    packet = {"status": "none" if lead == "NONE" else ("ready" if gaps_out["evidence_sufficient"] else "hold"),
              "sections": [{"heading": "Cover letter", "claims": packet_claims}] if packet_claims else []}
    req = None
    if data["request"]:
        gap = next((g["code"] for g in gaps_out["gaps"] if g["code"] in REQUESTS()), None)
        req = {"to": data["request_to"] or "clinician", "title": ASK_TITLE.get(data["request_to"] or "", "Request for documentation"),
               "gap": gap, "claims": [norm(c, "Q", i) for i, c in enumerate(data["request"])]}
    member = [norm(c, "M", i) for i, c in enumerate(data["member"])]
    return {"packet": packet, "request": req, "member_en": member}


def run(case, intake_out, extract_out, rules_out, gaps_out, meter, use_llm=True, outcome_out=None):
    # Recover / Transition framing is template-driven (fixed, reviewed wording that never promises an outcome),
    # so those cases use the deterministic drafter as their base.
    if use_llm and (outcome_out or {}).get("outcome", "retain") == "retain":
        try:
            return frame(case, llm(case, intake_out, extract_out, rules_out, gaps_out, meter), outcome_out), "llm", None
        except LLMUnavailable as e:
            return frame(case, deterministic(case, intake_out, extract_out, rules_out, gaps_out), outcome_out), "deterministic", str(e)
    return frame(case, deterministic(case, intake_out, extract_out, rules_out, gaps_out), outcome_out), "deterministic", None


# ------------------------------------------------------------------ translation (after verification)
TR_SYSTEM = """Translate each sentence for a health-plan member into {lang}. Plain language, warm, 6th-grade level.
Keep dates, amounts and numbers exactly as written. Keep the name "{agency}" untranslated. Do not add,
remove or soften any information. Return one translation per input sentence, same order."""
TR_SCHEMA = {"type": "object", "properties": {"sentences": {"type": "array", "items": {"type": "string"}}},
             "required": ["sentences"], "additionalProperties": False}


def translate(member_claims, lang, meter, use_llm=True):
    """Returns (list of {claim_id, text, en}, engine)."""
    if lang == "en":
        return [{"claim_id": c["claim_id"], "text": c["text"], "en": c["text"]} for c in member_claims], "none"
    if all(c.get("template") for c in member_claims):
        tmpl = [{"claim_id": c["claim_id"], "text": render(c["template"], lang), "en": c["text"]} for c in member_claims]
    else:
        tmpl = None
    if use_llm:
        try:
            data, _ = call_json("translate", TR_SYSTEM.format(lang=config.LANGUAGES.get(lang, lang), agency=rulebook.program()["agency"]),
                                "\n".join(f"{i + 1}. {c['text']}" for i, c in enumerate(member_claims)), TR_SCHEMA,
                                max_tokens=8000, meter=meter)
            if len(data["sentences"]) == len(member_claims):
                return [{"claim_id": c["claim_id"], "text": t, "en": c["text"]} for c, t in zip(member_claims, data["sentences"])], "llm"
        except LLMUnavailable:
            pass
    if tmpl:
        return tmpl, "template"
    return [{"claim_id": c["claim_id"], "text": c["text"], "en": c["text"]} for c in member_claims], "untranslated"
