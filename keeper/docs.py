"""Document loading and quote grounding helpers."""
import base64
import io
import re
import unicodedata


def normalize(s):
    s = unicodedata.normalize("NFKC", s or "")
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = s.replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", s).strip().lower()


def numbered(text):
    """Text with 1-based line numbers, as the LLM sees it."""
    return "\n".join(f"{i:>3}| {line}" for i, line in enumerate(text.splitlines(), 1))


def find_line(text, quote):
    """1-based line number where quote starts, or None if the quote is not in the document."""
    q = normalize(quote)
    if not q:
        return None
    lines = text.splitlines()
    for i, line in enumerate(lines):
        window = normalize(" ".join(lines[i:i + 6]))
        if window.startswith(q[: max(8, min(len(q), 40))]) or q in normalize(line):
            if q in window:
                return i + 1
    return 1 if q in normalize(text) else None


def quote_in(text, quote):
    q = normalize(quote)
    return bool(q) and q in normalize(text)


WATERMARK_PREFIX = "SYNTHETIC SAMPLE"


def pdf_to_text(data):
    """Layout-aware PDF text: rebuild each visual line by grouping words at the same height, left to right,
    so form fields ("Pay period:" ... "09/01/2026 - 09/15/2026") stay on one line."""
    try:
        import fitz
    except ImportError:
        from pypdf import PdfReader

        return "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(data)).pages)
    out = []
    with fitz.open(stream=data, filetype="pdf") as doc:
        for page in doc:
            rows = []
            for x0, y0, x1, y1, word, *_ in sorted(page.get_text("words"), key=lambda w: (w[3], w[0])):
                if rows and abs(rows[-1][0] - y1) <= 3:
                    rows[-1][1].append((x0, word))
                else:
                    rows.append([y1, [(x0, word)]])
            for _, words in rows:
                line = " ".join(w for _, w in sorted(words))
                if not line.startswith(WATERMARK_PREFIX):
                    out.append(line)
    return "\n".join(out)


def image_to_text(data, media_type):
    """OCR via Claude vision (live mode only)."""
    from . import config
    from .llm import LLMUnavailable, _get_client

    if config.MODE != "live":
        raise LLMUnavailable("Image documents need live mode (Claude vision) for transcription")
    resp = _get_client().messages.create(
        model=config.MODELS["extract"],
        max_tokens=8000,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": media_type,
                                         "data": base64.b64encode(data).decode()}},
            {"type": "text", "text": "Transcribe this document exactly, line by line, preserving the original "
                                     "language. Output only the transcription."},
        ]}],
    )
    return next(b.text for b in resp.content if getattr(b, "type", "") == "text")
