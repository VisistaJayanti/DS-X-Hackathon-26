"""Stage 1 - Intake: classify each document."""
import re

from .. import rulebook
from ..llm import LLMUnavailable, call_json
from ..textutil import guess_language

def doc_types_list():
    return rulebook.active()["doc_types"]


def system_prompt():
    prog = rulebook.program()
    return ("You are the intake agent in Coverage Keeper, which helps health-plan care coordinators and navigators keep "
            f"eligible members from losing coverage over paperwork. Program: {prog['domain_context']}\n"
            "Classify each document into exactly one type. All data is synthetic.\nDocument types: " + ", ".join(doc_types_list()))


def schema():
    return {
        "type": "object",
        "properties": {"documents": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "doc_id": {"type": "string"},
                "doc_type": {"type": "string", "enum": doc_types_list()},
                "language": {"type": "string", "description": "ISO 639-1 code of the document's language"},
                "summary": {"type": "string", "description": "one short line, no personal identifiers"},
            },
            "required": ["doc_id", "doc_type", "language", "summary"], "additionalProperties": False}}},
        "required": ["documents"], "additionalProperties": False,
    }


def classify_rules(doc):
    t = doc["text"].lower()
    for dtype, pat in rulebook.active()["doc_keywords"]:
        if re.search(pat, t):
            return dtype
    return "other"


def run(case, meter, use_llm=True):
    documents = case["documents"]
    result, engine, note = None, "deterministic", None
    if use_llm:
        user = "\n\n".join(f"<document id=\"{d['doc_id']}\" filename=\"{d['filename']}\">\n{d['text']}\n</document>"
                           for d in documents)
        try:
            data, _ = call_json("intake", system_prompt(), user, schema(), max_tokens=4000, meter=meter)
            by_id = {x["doc_id"]: x for x in data["documents"]}
            result = [{"doc_id": d["doc_id"], "filename": d["filename"],
                       "doc_type": by_id.get(d["doc_id"], {}).get("doc_type", classify_rules(d)),
                       "language": by_id.get(d["doc_id"], {}).get("language", guess_language(d["text"])),
                       "summary": by_id.get(d["doc_id"], {}).get("summary", "")} for d in documents]
            engine = "llm"
        except LLMUnavailable as e:
            note = str(e)
    if result is None:
        result = [{"doc_id": d["doc_id"], "filename": d["filename"], "doc_type": classify_rules(d),
                   "language": guess_language(d["text"]), "summary": d["text"].strip().splitlines()[0][:80]}
                  for d in documents]
    for r, d in zip(result, documents):
        r["lines"] = len(d["text"].splitlines())
    return {"documents": result}, engine, note


def doc_types(intake_out):
    return {d["doc_id"]: d["doc_type"] for d in intake_out["documents"]}

