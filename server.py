"""Coverage Keeper web app. Run: python server.py  (then open http://127.0.0.1:8000)"""
import json
import os
import queue
import threading
import uuid
from datetime import date
from pathlib import Path

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from keeper import config, crypto, doccheck, docs, geo, matcher, pipeline, plan, rulebook
from keeper.textutil import age_on
from keeper.llm import LLMUnavailable

ROOT = Path(__file__).resolve().parent
CASES = ROOT / "data" / "cases"
CUSTOM = ROOT / "data" / "custom"  # navigator-entered cases; git-ignored
app = FastAPI(title="Coverage Keeper")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
(ROOT / "data" / "documents").mkdir(parents=True, exist_ok=True)
app.mount("/documents", StaticFiles(directory=ROOT / "data" / "documents"), name="documents")  # rendered synthetic PDFs/PNGs

MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB per document
MAX_FILES = 10
ALLOWED_EXT = (".pdf", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".txt", ".md")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Browser-side hardening. Document responses are never cached, and the app can't be framed by other sites."""
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Content-Security-Policy"] = "frame-ancestors 'none'; object-src 'none'; base-uri 'self'"
    if request.url.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


def load_case(cid):
    if not cid.isalnum():
        raise HTTPException(400, "bad case id")
    for d in (CASES, CUSTOM):
        p = d / f"{cid}.json"
        if p.exists():
            return crypto.read_json(p)  # uploaded cases are encrypted at rest; synthetic ones are plain JSON
    raise HTTPException(404, "case not found")


def save_custom(case):
    crypto.write_json(CUSTOM / f"{case['case_id']}.json", case)


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/api/status")
def status():
    return {"mode": config.MODE, "api_key": bool(config.keys_present()), "providers": config.keys_present(),
            "preset": config.PRESET, "models": config.MODELS,
            "as_of": config.AS_OF.isoformat(), "languages": config.LANGUAGES}


@app.get("/api/cases")
def cases():
    out = []
    for d in (CUSTOM, CASES):
        if not d.exists():
            continue
        for p in sorted(d.glob("*.json")):
            try:
                c = crypto.read_json(p)
            except ValueError:  # encrypted with a different key
                continue
            out.append({"case_id": c["case_id"], "title": c["title"], "split": c.get("split", "custom"),
                        "name": c["member"]["name"], "language": c["member"].get("language", "en"),
                        "n_docs": len(c["documents"])})
    return out


@app.get("/api/cases/{cid}")
def case(cid: str):
    c = load_case(cid)
    for d in c["documents"]:
        img = ROOT / "data" / "documents" / cid / f"{d['doc_id']}.png"
        if img.exists():
            d["image"] = f"/documents/{cid}/{d['doc_id']}.png"
            d["pdf"] = f"/documents/{cid}/{d['doc_id']}.pdf"
    return c


class NewCase(BaseModel):
    title: str
    member: dict
    documents: list


@app.post("/api/cases")
def create_case(body: NewCase):
    CUSTOM.mkdir(parents=True, exist_ok=True)
    cid = "X" + uuid.uuid4().hex[:6].upper()
    m = dict(body.member)
    m.setdefault("lookback_months", ["2026-07", "2026-08", "2026-09"])
    m.setdefault("notice_type", "Request for Information (RFI)")
    c = {"case_id": cid, "title": body.title, "split": "custom", "member": m,
         "documents": [{"doc_id": f"D{i + 1}", "filename": d.get("filename", f"doc{i + 1}.txt"), "text": d["text"]}
                       for i, d in enumerate(body.documents) if d.get("text", "").strip()]}
    save_custom(c)
    return c


def _file_to_text(name, data):
    name = name.lower()
    if name.endswith(".pdf"):
        return docs.pdf_to_text(data)
    if name.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
        mt = "image/jpeg" if name.endswith(("jpg", "jpeg")) else f"image/{name.rsplit('.', 1)[1]}"
        try:
            return docs.image_to_text(data, mt)
        except LLMUnavailable:
            return ""  # kept as an unreadable document so the checker flags it
    return data.decode("utf-8", errors="replace")


@app.post("/api/upload")
async def upload(profile: str = Form(...), files: list[UploadFile] = File(default=[])):
    """Feature 1: upload documents + member profile. Files are read in memory, only the extracted text is kept,
    and the case is stored encrypted. Returns the case id, the policy matches and the document check."""
    try:
        prof = json.loads(profile)
    except json.JSONDecodeError:
        raise HTTPException(400, "profile must be JSON")
    if len(files) > MAX_FILES:
        raise HTTPException(400, f"at most {MAX_FILES} files")
    documents = []
    for i, f in enumerate(files):
        name = f.filename or f"doc{i + 1}"
        if not name.lower().endswith(ALLOWED_EXT):
            raise HTTPException(400, f"{name}: file type not allowed")
        data = await f.read(MAX_FILE_BYTES + 1)
        if len(data) > MAX_FILE_BYTES:
            raise HTTPException(400, f"{name}: larger than 10 MB")
        documents.append({"doc_id": f"D{i + 1}", "filename": name, "text": _file_to_text(name, data)})
        del data  # raw bytes are never written to disk

    member = {k: (prof.get(k) or None) for k in ("name", "dob", "nationality", "country", "region", "coverage_start",
                                                 "coverage_end", "tier", "notice_received_date")}
    member["name"] = member["name"] or "Uploaded member"
    member["language"] = prof.get("language") or "en"
    if member["dob"]:
        try:
            member["age"] = age_on(date.fromisoformat(member["dob"]), config.AS_OF)
        except ValueError:
            raise HTTPException(400, "dob must be YYYY-MM-DD")
    member.setdefault("lookback_months", ["2026-07", "2026-08", "2026-09"])
    member.setdefault("notice_type", "Request for Information (RFI)")
    cid = "U" + uuid.uuid4().hex[:6].upper()
    case = {"case_id": cid, "title": f"Upload: {member['name']}", "split": "custom", "member": member,
            "documents": documents, "uploaded": True}
    m = matcher.match(case)
    case["pack"] = next((r["pack"] for r in m["results"] if r["runnable"] and r["status"] != "no_match"), None)
    save_custom(case)
    return {"case_id": cid, "match": m, "check": _check(case, m["best"] or m["results"][0]["pack"], m)}


def _check(case, pack_id, m=None):
    rulebook.use(pack_id)
    pack = rulebook.active()
    rulebook.use(None)
    m = m or matcher.match(case)
    crit = next((r for r in m["results"] if r["pack"] == pack_id), None)
    out = doccheck.check(case, pack, crit)
    used = {f["rule_id"] for f in out["flags"] if f.get("rule_id")}
    out["rules"] = {r["id"]: {k: r.get(k) for k in ("cite", "quote", "needs_confirmation", "source_status")}
                    for r in pack["rulebook"]["rules"] if r["id"] in used}
    out["pack_name"] = pack["name"]
    return out


@app.get("/api/match/{cid}")
def match(cid: str):
    """Feature 2: rank every policy pack for this case."""
    return matcher.match(load_case(cid))


@app.get("/api/check/{cid}")
def check(cid: str, pack: str = ""):
    """Features 1 + 3: required documents, flags and suggested corrections against one pack."""
    c = load_case(cid)
    m = matcher.match(c)
    return _check(c, pack or m["best"] or m["results"][0]["pack"], m)


@app.delete("/api/cases/{cid}")
def delete_case(cid: str):
    """Let a user remove their uploaded documents completely."""
    p = CUSTOM / f"{cid}.json"
    if not cid.isalnum() or not p.exists():
        raise HTTPException(404, "case not found")
    p.unlink()
    return {"deleted": cid}


@app.get("/api/countries")
def countries():
    return {"countries": geo.options(), "tiers": matcher.TIERS}


@app.post("/api/extract-text")
async def extract_text(file: UploadFile = File(...)):
    data = await file.read()
    name = (file.filename or "").lower()
    try:
        if name.endswith(".pdf"):
            text = docs.pdf_to_text(data)
        elif name.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
            mt = "image/jpeg" if name.endswith(("jpg", "jpeg")) else f"image/{name.rsplit('.', 1)[1]}"
            text = docs.image_to_text(data, mt)
        else:
            text = data.decode("utf-8", errors="replace")
    except LLMUnavailable as e:
        raise HTTPException(400, str(e))
    return {"filename": file.filename, "text": text}


@app.get("/api/run/{cid}")
def run(cid: str, lang: str = "", verifier: int = 1, engine: str = "auto", pack: str = ""):
    c = load_case(cid)
    if pack:
        c["pack"] = pack
    pid = c.get("pack") or rulebook.DEFAULT
    if not rulebook.available_ids().get(pid, False):
        msg = {"event": "error", "error": f"The '{pid}' pack only supports matching and document checks, not the full "
                                          f"agent pipeline. Use the Upload tab's results, or pick a runnable pack."}
        return StreamingResponse(iter([f"data: {json.dumps(msg)}\n\n"]), media_type="text/event-stream")
    use_llm = None if engine == "auto" else (engine == "llm")
    q = queue.Queue()

    def work():
        try:
            trace = pipeline.run(c, use_llm=use_llm, use_verifier=bool(verifier), lang=lang or None, on_event=q.put)
            q.put({"event": "trace", "trace": trace})
        except Exception as e:  # surface errors to the UI instead of hanging the stream
            q.put({"event": "error", "error": f"{type(e).__name__}: {e}"})
        q.put(None)

    threading.Thread(target=work, daemon=True).start()

    def stream():
        while True:
            ev = q.get()
            if ev is None:
                break
            yield f"data: {json.dumps(ev, ensure_ascii=False, default=str)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.get("/api/packs")
def packs():
    return rulebook.available()


@app.get("/api/packs/{pack_id}")
def get_pack(pack_id: str):
    rulebook.use(pack_id)
    p = dict(rulebook.active())
    rulebook.use(None)
    return p


@app.get("/api/plan")
def get_plan(top_k: int = 40):
    return plan.plan(top_k)


@app.get("/api/eval")
def get_eval():
    p = ROOT / "eval" / "results.json"
    if not p.exists():
        return JSONResponse({"available": False})
    return json.loads(p.read_text(encoding="utf-8"))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"Coverage Keeper  mode={config.MODE}  as_of={config.AS_OF}  ->  http://127.0.0.1:{port}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
