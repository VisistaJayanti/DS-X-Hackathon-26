"""Active policy pack. All program-specific content (scope, pathways + thresholds, exemptions, gap codes and
fixes, deadlines, document types, notice conventions, languages, cited rules) lives in packs/<id>/.
The agents only read it through this module."""
import json
import os
import re
import threading
from functools import lru_cache
from pathlib import Path

PACKS = Path(__file__).resolve().parent.parent / "packs"
_state = threading.local()
DEFAULT = os.environ.get("PP_PACK", "masshealth_ce_2027")


def available():
    out = []
    for d in sorted(PACKS.iterdir()):
        if (d / "pack.json").exists():
            p = json.loads((d / "pack.json").read_text(encoding="utf-8"))
            out.append({k: p.get(k) for k in ("id", "name", "line_of_business", "jurisdiction", "illustrative", "summary")})
    return out


CFR_CITE = re.compile(r"(\d+)\s+CFR\s+(\d+\.\d+)((?:\([0-9A-Za-z]+\))*)")


def rule_url(rule, sources):
    """Deep link for a rule: a federal citation goes to that section and paragraph on eCFR; anything else to its source page."""
    m = CFR_CITE.search(rule.get("cite", ""))
    if m:
        title, sec, paras = m.groups()
        return f"https://www.ecfr.gov/current/title-{title}/section-{sec}" + (f"#p-{sec}{paras}" if paras else "")
    return sources.get(rule.get("source"), {}).get("url")


@lru_cache(maxsize=None)
def _load(pack_id):
    d = PACKS / pack_id
    pack = json.loads((d / "pack.json").read_text(encoding="utf-8"))
    pack["rulebook"] = json.loads((d / "rules.json").read_text(encoding="utf-8"))
    for r in pack["rulebook"]["rules"]:
        r["url"] = rule_url(r, pack["rulebook"]["_meta"]["sources"])
    return pack


def use(pack_id):
    """Select the pack for the current thread (each pipeline run sets it from the case)."""
    _state.pack = pack_id or DEFAULT


def active():
    return _load(getattr(_state, "pack", None) or DEFAULT)


def load():
    return active()["rulebook"]


def rules():
    return {r["id"]: r for r in load()["rules"]}


def pathways():
    return active()["pathways"]


def pathway(pid):
    return next(p for p in pathways() if p["id"] == pid)


def rule_for(pid):
    rid = pathway(pid)["rule_id"]
    return rules()[rid]


def gap(code):
    return active()["gap_codes"][code]


def program():
    return active()["program"]


def source(rule):
    return load()["_meta"]["sources"][rule["source"]]
