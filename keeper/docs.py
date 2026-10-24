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


def pdf_to_text(data):
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    return "\n".join((p.extract_text() or "") for p in reader.pages)


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
