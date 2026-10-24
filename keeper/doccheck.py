"""Document checks for features 1 and 3.

1. Required documents: every document a policy pack lists in `required_documents` must be present among the
   uploads; anything missing is flagged with what to upload.
3. Flags + corrections: facts read from the documents (date of birth, expiry dates, nationality, name) are
   compared with the member's profile and with the pack's criteria; each problem gets a suggested correction,
   the document line it came from, and the rule it relates to.

Deterministic on purpose: it runs offline, is reproducible, and never decides eligibility. It only points at
things a coordinator should check.
"""
import re
from datetime import date

from . import config, geo
from .textutil import age_on, find_dates

RE_DOB = re.compile(r"date of birth|\bd\.?o\.?b\b|birth ?date|born on|fecha de nacimiento|data de nascimento", re.I)
RE_EXPIRY = re.compile(r"expir|valid until|valid through|valid thru|vence|vencimiento|validade", re.I)
RE_NATIONALITY = re.compile(r"(?:nationality|citizenship|nacionalidad|nacionalidade)\s*[:\-]?\s*([A-Za-zÀ-ÿ .']{3,40})", re.I)
RE_NAME = re.compile(r"^\s*(?:full name|name|patient name|patient|member|re|nombre|nome)\s*[:\-]\s*(.{3,60})$", re.I | re.M)
MIN_TEXT_CHARS = 25


def _parse_date(s):
    try:
        return date.fromisoformat(s) if s else None
    except ValueError:
        return None


def _lines(doc):
    return doc.get("text", "").splitlines()


def extract_facts(documents):
    """Read simple, checkable facts from each document, keeping the exact line they came from."""
    facts = []
    for d in documents:
        for i, line in enumerate(_lines(d), 1):
            base = {"doc_id": d["doc_id"], "line": i, "quote": line.strip()[:200]}
            if RE_DOB.search(line):
                ds = find_dates(line)
                if ds:
                    facts.append({**base, "type": "dob", "value": ds[0].isoformat()})
            if RE_EXPIRY.search(line):
                ds = find_dates(line)
                if ds:
                    facts.append({**base, "type": "expiry", "value": ds[-1].isoformat()})
            m = RE_NATIONALITY.search(line)
            if m:
                raw = m.group(1).strip()
                facts.append({**base, "type": "nationality", "value": geo.to_code(raw) or raw})
        for m in RE_NAME.finditer(d.get("text", "")):
            line_no = d["text"][: m.start()].count("\n") + 1
            value = re.split(r"\s{2,}|\bdob\b|date of birth", m.group(1), flags=re.I)[0].strip(" ,;")
            facts.append({"doc_id": d["doc_id"], "line": line_no, "quote": m.group(0).strip()[:200], "type": "name",
                          "value": value})
        dated = find_dates(d.get("text", ""))
        if dated:
            facts.append({"doc_id": d["doc_id"], "line": None, "quote": "", "type": "latest_date",
                          "value": max(dated).isoformat()})
    return facts


def about_member(doc_id, facts, member_name):
    """True unless the document clearly names someone else (e.g. a parent's medical letter).
    Used so another person's date of birth or nationality is never treated as the member's."""
    names = [f["value"] for f in facts if f["type"] == "name" and f["doc_id"] == doc_id]
    return not names or not member_name or any(_same_name(member_name, n) for n in names)


def member_facts(facts, member_name, kind):
    return [f for f in facts if f["type"] == kind and about_member(f["doc_id"], facts, member_name)]


def _find_in_docs(documents, pattern):
    """First (doc_id, line, quote) whose text or filename matches the pattern."""
    rx = re.compile(pattern, re.I)
    for d in documents:
        if rx.search(d.get("filename", "")):
            return {"doc_id": d["doc_id"], "line": None, "quote": d.get("filename", "")}
        for i, line in enumerate(_lines(d), 1):
            if rx.search(line):
                return {"doc_id": d["doc_id"], "line": i, "quote": line.strip()[:200]}
    return None


def required_documents(pack, documents):
    """Which required documents were found, and where."""
    out = []
    for req in pack.get("required_documents", []):
        hit = _find_in_docs(documents, req["keywords"]) if documents else None
        out.append({"id": req["id"], "label": req["label"], "present": bool(hit), "found_in": hit,
                    "why": req.get("why", ""), "fix": req.get("fix", ""), "rule_id": req.get("rule_id")})
    return out


def _flag(code, severity, title, detail, fix, src=None, rule_id=None):
    f = {"code": code, "severity": severity, "title": title, "detail": detail, "fix": fix, "rule_id": rule_id,
         "doc_id": None, "line": None, "quote": ""}
    if src:
        f.update({k: src.get(k) for k in ("doc_id", "line", "quote")})
    return f


def _same_name(a, b):
    stop = {"dob", "illustrative", "composite", "mr", "mrs", "ms", "dr"}
    ta = {t for t in re.findall(r"[a-zà-ÿ]+", a.lower()) if len(t) > 1} - stop
    tb = {t for t in re.findall(r"[a-zà-ÿ]+", b.lower()) if len(t) > 1} - stop
    return bool(ta & tb)


def check(case, pack, criteria=None):
    """All flags for one case against one pack. `criteria` is the matcher's result for this pack (optional)."""
    documents = case.get("documents", [])
    profile = case.get("member", {})
    flags = []

    # --- feature 1: documents must be present -------------------------------------------------
    if not documents:
        flags.append(_flag("NO_DOCUMENTS", "error", "No documents uploaded",
                           "Nothing was uploaded, so nothing can be checked against the policy.",
                           "Upload at least the documents listed under 'Required documents'."))
    for d in documents:
        if len(d.get("text", "").strip()) < MIN_TEXT_CHARS:
            flags.append(_flag("UNREADABLE_DOCUMENT", "error", f"{d.get('filename', d['doc_id'])} could not be read",
                               "Little or no text could be read from this file (a blurry photo, a scanned PDF without text, "
                               "or an image uploaded while live mode is off).",
                               "Upload a clearer photo or a text-based PDF, or turn on live mode so images are transcribed.",
                               {"doc_id": d["doc_id"], "line": None, "quote": ""}))
    reqs = required_documents(pack, documents)
    for r in reqs:
        if not r["present"]:
            flags.append(_flag("MISSING_DOCUMENT", "error", f"Missing: {r['label']}", r["why"], r["fix"], rule_id=r["rule_id"]))

    # --- feature 3: facts in the documents vs. the profile and the policy -------------------------
    facts = extract_facts(documents)
    today = config.AS_OF
    cov_start = _parse_date(profile.get("coverage_start"))
    cov_end = _parse_date(profile.get("coverage_end"))

    p_name = (profile.get("name") or "").strip()
    p_dob = _parse_date(profile.get("dob"))
    for f in member_facts(facts, p_name, "dob"):
        if p_dob and f["value"] != p_dob.isoformat():
            flags.append(_flag("DOB_MISMATCH", "error", "Date of birth does not match",
                               f"The document says {f['value']}; the form says {p_dob.isoformat()}.",
                               "Check which date is correct. Fix the form, or ask the issuer to correct the document. "
                               "Insurers usually reject applications where dates of birth differ.", f))

    for f in (x for x in facts if x["type"] == "expiry"):
        exp = date.fromisoformat(f["value"])
        if exp < today:
            flags.append(_flag("EXPIRED_DOCUMENT", "error", "Document has expired",
                               f"It expired on {exp.isoformat()}.",
                               "Upload a current version (renewed passport, ID, permit or authorization).", f))
        elif cov_end and exp < cov_end:
            flags.append(_flag("EXPIRES_DURING_COVERAGE", "warning", "Document expires before coverage ends",
                               f"It expires on {exp.isoformat()}, before the coverage end date {cov_end.isoformat()}.",
                               "Plan to renew it before it expires, or shorten the requested coverage period.", f))

    max_age_days = pack.get("document_expiry_days")
    if max_age_days:
        for f in (x for x in facts if x["type"] == "latest_date"):
            age_days = (today - date.fromisoformat(f["value"])).days
            if age_days > max_age_days:
                flags.append(_flag("STALE_DOCUMENT", "warning", "Document may be too old",
                                   f"The most recent date in it is {f['value']} ({age_days} days ago); this policy usually "
                                   f"wants documents from the last {max_age_days} days.",
                                   "Upload a more recent version (for example, the latest pay stub or an updated letter).", f))

    p_nat = geo.to_code(profile.get("nationality"))
    for f in member_facts(facts, p_name, "nationality"):
        doc_nat = f["value"] if len(str(f["value"])) == 2 else geo.to_code(f["value"])
        if p_nat and doc_nat and doc_nat != p_nat:
            flags.append(_flag("NATIONALITY_MISMATCH", "error", "Nationality does not match",
                               f"The document shows {geo.name(doc_nat)}; the form says {geo.name(p_nat)}.",
                               "Correct the nationality in the form, or upload the passport for the nationality you entered.", f))

    if p_name:
        for f in (x for x in facts if x["type"] == "name"):
            if not _same_name(p_name, f["value"]):
                flags.append(_flag("NAME_MISMATCH", "warning", "Name may not match",
                                   f"The document names '{f['value']}'; the form says '{p_name}'.",
                                   "If this document is about someone else (for example a family member), that's fine. "
                                   "Otherwise make the names match, or upload proof of a name change.", f))

    if cov_start and cov_end and cov_end <= cov_start:
        flags.append(_flag("TIMELINE_INVALID", "error", "Coverage dates are reversed",
                           f"Coverage ends ({cov_end.isoformat()}) on or before it starts ({cov_start.isoformat()}).",
                           "Fix the coverage start and end dates in the form."))

    # Policy criteria that failed or need attention become flags too (age, country, nationality, timeline, tier).
    for c in (criteria or {}).get("criteria", []):
        if c["status"] in ("fail", "warn", "unknown"):
            flags.append(_flag(f"CRITERION_{c['criterion'].upper()}", "error" if c["status"] == "fail" else "warning",
                               c["title"], c["detail"], c.get("fix", ""), c.get("source"), c.get("rule_id")))

    order = {"error": 0, "warning": 1}
    flags.sort(key=lambda f: order.get(f["severity"], 2))
    return {"pack": pack["id"], "required_documents": reqs, "facts": facts, "flags": flags,
            "counts": {"errors": sum(f["severity"] == "error" for f in flags),
                       "warnings": sum(f["severity"] == "warning" for f in flags)},
            "note": "Decision support only: these flags point at things to check. The insurer decides eligibility."}


def doc_age(dob, on=None):
    return age_on(dob, on or config.AS_OF)
