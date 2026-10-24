"""Coverage Keeper web app. Run: python server.py  (then open http://127.0.0.1:8000)"""
import json
import os
import queue
import threading
import uuid
from pathlib import Path

import uvicorn
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from keeper import config, docs, pipeline, plan, rulebook
from keeper.llm import LLMUnavailable

ROOT = Path(__file__).resolve().parent
CASES = ROOT / "data" / "cases"
CUSTOM = ROOT / "data" / "custom"  # navigator-entered cases; git-ignored
app = FastAPI(title="Coverage Keeper")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
(ROOT / "data" / "documents").mkdir(parents=True, exist_ok=True)
app.mount("/documents", StaticFiles(directory=ROOT / "data" / "documents"), name="documents")  # rendered synthetic PDFs/PNGs


def load_case(cid):
    for d in (CASES, CUSTOM):
        p = d / f"{cid}.json"
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    raise HTTPException(404, "case not found")


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
            c = json.loads(p.read_text(encoding="utf-8"))
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
    (CUSTOM / f"{cid}.json").write_text(json.dumps(c, indent=2, ensure_ascii=False), encoding="utf-8")
    return c


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
    print(f"Coverage Keeper  mode={config.MODE}  as_of={config.AS_OF}  ->  http://127.0.0.1:8000")
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", 8000)), log_level="warning")
