"""Document loading and quote grounding helpers."""
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
    """OCR via the configured vision model (config.MODELS['ocr'], live mode only)."""
    from .llm import transcribe_image

    return transcribe_image(data, media_type, "Transcribe this document exactly, line by line, preserving the original "
                                              "language. Output only the transcription.")
