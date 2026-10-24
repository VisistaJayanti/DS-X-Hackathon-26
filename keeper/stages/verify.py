"""Stage 6 - Verifier: every claim must be backed by an exact document quote and/or a rulebook rule.

Checks, in order:
  1. structure     - fact claims need a doc_id + quote; finding/rule claims need a known rule_id
  2. grounding     - the quote appears verbatim in that document; cited fact_ids exist
  3. numbers       - every number in the claim appears in its support (quotes, rule text, computed results)
  4. guardrail     - no eligibility-decision language ("is eligible", "is exempt", "approved", "guaranteed")
  5. entailment    - (live mode) an LLM checks the quote actually supports the sentence
Claims failing 1-4 are removed; entailment 'unsupported' is removed, 'partial' is flagged.
"""
import json
import re

from .. import docs as D
from .. import rulebook
from ..llm import LLMUnavailable, call_json

DECISION = re.compile(r"\b(is|are|will be|has been)\s+(eligible|exempt|approved)\b|\bguarantee|\bwill (keep|not lose)\b|"
                      r"\byou qualify\b|\bqualifies for\b", re.I)
NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _nums(s):
    out = set()
    for m in NUM.findall(s or ""):
        v = m.replace(",", "").rstrip(".")
        try:
            f = float(v)
        except ValueError:
            continue
        out.add(f"{f:g}")
        if "." not in v and len(v) <= 2:
            out.add(str(int(v)))
    return out


def _support_text(claim, ctx):
    parts = []
    if claim.get("quote"):
        parts.append(claim["quote"])
    for fid in claim.get("fact_ids", []) or []:
        f = ctx["facts"].get(fid)
        if f:
            parts.append(f["quote"])
            parts.append(json.dumps({k: v for k, v in f.items() if k not in ("quote",)}))
    rid = claim.get("rule_id")
    if rid and rid in ctx["rules"]:
        r = ctx["rules"][rid]
        parts += [r["name"], r["quote"], r.get("quote_2", ""), r["cite"]]
        for p in ctx["pathways"]:
            if p["rule_id"] == rid:
                parts += p["reasons"] + [json.dumps({k: p.get(k) for k in ("computed", "month")})]
    parts.append(ctx["always"])
    return " ".join(parts)


def check_claim(claim, ctx):
    """Deterministic checks. Returns list of failure reasons (empty = passes)."""
    kind, why = claim.get("kind"), []
    if kind == "boilerplate":
        return []
    if kind == "fact":
        doc = ctx["docs"].get(claim.get("doc_id"))
        if not doc or not claim.get("quote"):
            why.append("fact claim without a document quote")
        elif not D.quote_in(doc["text"], claim["quote"]):
            why.append(f"quote not found in {claim.get('doc_id')}")
    elif kind in ("finding", "rule"):
        if claim.get("rule_id") not in ctx["rules"]:
            why.append(f"unknown rule_id {claim.get('rule_id')!r}")
        missing = [f for f in claim.get("fact_ids", []) or [] if f not in ctx["facts"]]
        if missing:
            why.append(f"cites unknown facts {missing}")
    elif kind != "request":
        why.append(f"unknown claim kind {kind!r}")
    extra = _nums(claim["text"]) - _nums(_support_text(claim, ctx))
    if extra:
        why.append(f"numbers not in support: {sorted(extra)}")
    if DECISION.search(claim["text"]):
        why.append("eligibility-decision language")
    return why


ENTAIL_SYSTEM = """You are the verification agent. For each claim, decide whether its SUPPORT (document quotes,
rule text, computed results) fully supports the CLAIM sentence. "supported": every factual assertion is in the
support. "partial": mostly supported but adds a detail not in the support. "unsupported": asserts something the
support does not say, or contradicts it. Requests ("please provide...") are supported if they ask for
something; they assert nothing. Be strict. All data is synthetic."""
ENTAIL_SCHEMA = {"type": "object", "properties": {"verdicts": {"type": "array", "items": {
    "type": "object", "properties": {"claim_id": {"type": "string"}, "verdict": {"type": "string", "enum": ["supported", "partial", "unsupported"]},
                                     "reason": {"type": "string"}},
    "required": ["claim_id", "verdict", "reason"], "additionalProperties": False}}},
    "required": ["verdicts"], "additionalProperties": False}


def entail(claims, ctx, meter, stage="verify"):
    items = [{"claim_id": c["claim_id"], "claim": c["text"], "support": _support_text(c, ctx)[:3000]}
             for c in claims if c.get("kind") != "boilerplate"]
    if not items:
        return {}
    data, _ = call_json(stage, ENTAIL_SYSTEM, json.dumps(items, ensure_ascii=False, indent=1), ENTAIL_SCHEMA,
                        max_tokens=8000, meter=meter)
    return {v["claim_id"]: v for v in data["verdicts"]}


def _outcome_numbers(oc):
    """Dates and day counts the Outcome stage computed (windows, deadlines), as text."""
    if not oc:
        return ""
    rc, t = oc.get("reconsideration") or {}, oc.get("transition") or {}
    w = t.get("window") or {}
    vals = [rc.get(k) for k in ("termination_date", "ends", "days_left", "window_days", "days_since", "ask_third_party_by")]
    vals += [w.get(k) for k in ("opens", "closes", "avoid_gap_by")] + [t.get("coverage_end"), (t.get("change") or {}).get("date")]
    return " ".join(str(v) for v in vals if v is not None)


def context(case, extract_out, rules_out, gaps_out, outcome_out=None):
    dl = gaps_out.get("deadline") or {}
    m = case["member"]
    always = " ".join(str(x) for x in [m.get("age"), m.get("notice_received_date"), dl.get("due"), dl.get("days_left"), dl.get("ask_third_party_by"),
                                       " ".join(m.get("lookback_months", [])), "80 580 13 19 64 65 30", m.get("name")])
    always += " " + _outcome_numbers(outcome_out)
    always += " " + " ".join(f"{d['doc_id']} line {i}" for d in case["documents"] for i in range(1, len(d["text"].splitlines()) + 1))
    return {"docs": {d["doc_id"]: d for d in case["documents"]}, "facts": {f["fact_id"]: f for f in extract_out["facts"]},
            "rules": rulebook.rules(), "pathways": rules_out["pathways"], "always": always}


def run(case, extract_out, rules_out, gaps_out, draft_out, meter, use_llm=True, outcome_out=None):
    ctx = context(case, extract_out, rules_out, gaps_out, outcome_out)
    sections = [("packet", c) for s in draft_out["packet"]["sections"] for c in s["claims"]]
    if draft_out["request"]:
        sections += [("request", c) for c in draft_out["request"]["claims"]]
    sections += [("member", c) for c in draft_out["member_en"]]

    verdicts, engine, note = {}, "deterministic", None
    if use_llm:
        try:
            verdicts = entail([c for _, c in sections], ctx, meter)
            engine = "deterministic+llm"
        except LLMUnavailable as e:
            note = str(e)

    removed, flagged, keep = [], [], set()
    for where, c in sections:
        why = check_claim(c, ctx)
        v = verdicts.get(c["claim_id"])
        if v and v["verdict"] == "unsupported":
            why.append(f"LLM verifier: {v['reason']}")
        if why:
            removed.append({"where": where, "claim_id": c["claim_id"], "text": c["text"], "reasons": why})
        else:
            keep.add(c["claim_id"])
            if v and v["verdict"] == "partial":
                flagged.append({"where": where, "claim_id": c["claim_id"], "text": c["text"], "reasons": [f"LLM verifier: {v['reason']}"]})

    verified = {
        "packet": dict(draft_out["packet"], sections=[dict(s, claims=[c for c in s["claims"] if c["claim_id"] in keep])
                                                      for s in draft_out["packet"]["sections"]]),
        "request": (dict(draft_out["request"], claims=[c for c in draft_out["request"]["claims"] if c["claim_id"] in keep])
                    if draft_out["request"] else None),
        "member_en": [c for c in draft_out["member_en"] if c["claim_id"] in keep],
    }
    stats = {"claims": len(sections), "removed": len(removed), "flagged": len(flagged)}
    return {"verified": verified, "removed": removed, "flagged": flagged, "stats": stats}, engine, note
