"""Render every synthetic case document as a realistic-looking PDF + PNG page image.

ALL SYNTHETIC: every page carries a "SYNTHETIC SAMPLE" watermark and footer; names, organisations' letters,
IDs and numbers are invented. Layout follows the document type (letterhead, pay-stub form, handwritten-style
statement on lined paper, ID card) so the demo shows what a coordinator would actually receive.

Usage: python data/render_documents.py   -> data/documents/<case_id>/<doc_id>.pdf / .png
Requires PyMuPDF (pip install pymupdf).
"""
import json
import re
import sys
from pathlib import Path

import fitz  # PyMuPDF

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from keeper.stages.intake import classify_rules  # noqa: E402

OUT = ROOT / "data" / "documents"
W, H, M = 612, 792, 54
INK, GREY, LINE = (0.12, 0.14, 0.2), (0.42, 0.45, 0.52), (0.82, 0.84, 0.88)
BAND = {  # header colour per document type
    "pay_stub": (0.09, 0.32, 0.45), "gig_earnings_statement": (0.95, 0.35, 0.16), "employer_letter": (0.2, 0.25, 0.35),
    "clinician_letter": (0.05, 0.42, 0.42), "treatment_program_letter": (0.33, 0.25, 0.55),
    "hospital_discharge_or_prenatal": (0.1, 0.36, 0.62), "school_enrollment_letter": (0.45, 0.12, 0.16),
    "insurer_notice": (0.12, 0.3, 0.6), "snap_notice": (0.12, 0.3, 0.6), "va_rating_letter": (0.13, 0.22, 0.4),
    "ssa_disability_letter": (0.13, 0.22, 0.4), "foster_care_letter": (0.12, 0.3, 0.6), "release_paperwork": (0.25, 0.25, 0.25),
    "tribal_enrollment": (0.45, 0.28, 0.12), "volunteer_record": (0.18, 0.45, 0.25), "job_training_record": (0.18, 0.35, 0.55),
    "birth_record": (0.35, 0.3, 0.2),
}
KV = re.compile(r"^\s*([A-Za-zÀ-ÿ'()./ #-]{2,38}):\s+(.+)$")


def wrap(text, font, size, width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if fitz.get_text_length(t, fontname=font, fontsize=size) <= width:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


def watermark(page):
    for y in (300, 620):
        p = fitz.Point(120, y)
        page.insert_text(p, "SYNTHETIC SAMPLE", fontsize=54, fontname="hebo", color=(0.85, 0.2, 0.2),
                         fill_opacity=0.08, morph=(p, fitz.Matrix(-30)))
    page.insert_text((M, H - 24), "SYNTHETIC SAMPLE - generated for the Coverage Keeper demo. Not a real document; all names and "
                                  "numbers are invented.", fontsize=7, fontname="helv", color=GREY)


def split_header(lines, dtype):
    """Leading lines up to the first blank / key:value line form the letterhead."""
    head = []
    for l in lines:
        if not l.strip() or (KV.match(l) and head) or len(head) == 3:
            break
        head.append(l.strip())
    return head, lines[len(head):]


def body(page, lines, y, x0=M, x1=W - M, font="helv", size=10.5, lead=15, handwritten=False):
    sig_next = False
    for raw in lines:
        l = raw.rstrip()
        if not l.strip():
            y += lead * 0.6
            continue
        if re.fullmatch(r"[-\s]{6,}", l):
            page.draw_line((x0, y), (x1, y), color=LINE, width=0.8, dashes="[3 3] 0")
            y += lead
            continue
        m = KV.match(l)
        if m and not handwritten and len(m.group(2)) < 70:
            page.insert_text((x0, y), m.group(1).strip() + ":", fontsize=size - 1.5, fontname="helv", color=GREY)
            page.insert_text((x0 + 150, y), m.group(2).strip(), fontsize=size, fontname="hebo", color=INK)
            page.draw_line((x0 + 148, y + 4), (x1, y + 4), color=LINE, width=0.5)
            y += lead + 3
            continue
        f = font
        if sig_next and not handwritten:
            page.insert_text((x0, y + 4), l.split(",")[0], fontsize=17, fontname="tiit", color=(0.1, 0.15, 0.45))
            y += 22
            sig_next = False
        if re.match(r"^(Sincerely|Atentamente|Respectfully)", l):
            sig_next = True
        for w in wrap(l, f, size, x1 - x0):
            page.insert_text((x0, y), w, fontsize=size, fontname=f, color=(0.1, 0.13, 0.4) if handwritten else INK)
            y += lead
    return y


def render(doc, dtype, out_pdf):
    pdf = fitz.open()
    page = pdf.new_page(width=W, height=H)
    lines = doc["text"].splitlines()

    if dtype == "caregiver_attestation":  # handwritten-style statement on lined paper
        for yy in range(110, H - 60, 24):
            page.draw_line((M - 10, yy + 4), (W - M + 10, yy + 4), color=(0.75, 0.85, 0.95), width=0.6)
        page.draw_line((M - 18, 60), (M - 18, H - 50), color=(0.95, 0.6, 0.6), width=0.8)
        body(page, lines, 110, font="tiit", size=14, lead=24, handwritten=True)
    elif dtype in ("medicare_card", "id_card"):  # card
        r = fitz.Rect(M + 40, 120, W - M - 40, 360)
        page.draw_rect(r, color=(0.3, 0.4, 0.6), fill=(0.93, 0.95, 0.99), width=1.2, radius=0.06)
        page.draw_rect(fitz.Rect(r.x0, r.y0, r.x1, r.y0 + 44), color=None, fill=(0.12, 0.3, 0.6), radius=0.06)
        page.insert_text((r.x0 + 16, r.y0 + 28), lines[0], fontsize=14, fontname="hebo", color=(1, 1, 1))
        body(page, lines[1:], r.y0 + 74, x0=r.x0 + 16, x1=r.x1 - 16, size=10)
    else:  # letterhead / form
        head, rest = split_header(lines, dtype)
        col = BAND.get(dtype, (0.25, 0.3, 0.4))
        page.draw_rect(fitz.Rect(0, 0, W, 78), color=None, fill=col)
        page.draw_circle((M + 20, 39), 18, color=(1, 1, 1), fill=(1, 1, 1), fill_opacity=0.15, width=1.2)
        initials = "".join(w[0] for w in re.findall(r"[A-Za-z]+", head[0] if head else "Doc")[:2]).upper()
        page.insert_text((M + 9, 45), initials, fontsize=14, fontname="hebo", color=(1, 1, 1))
        if head:
            page.insert_text((M + 52, 36), head[0][:62], fontsize=15, fontname="hebo", color=(1, 1, 1))
        for i, h in enumerate(head[1:3]):
            page.insert_text((M + 52, 52 + 13 * i), h[:80], fontsize=9.5, fontname="helv", color=(0.92, 0.95, 1))
        if dtype == "pay_stub":
            page.draw_rect(fitz.Rect(M - 8, 96, W - M + 8, H - 60), color=LINE, width=0.8)
        body(page, rest, 112)
    watermark(page)
    pdf.save(out_pdf)
    page.get_pixmap(dpi=96).save(str(out_pdf.with_suffix(".png")))
    pdf.close()


def main():
    n = 0
    for p in sorted((ROOT / "data" / "cases").glob("*.json")):
        case = json.loads(p.read_text(encoding="utf-8"))
        d = OUT / case["case_id"]
        d.mkdir(parents=True, exist_ok=True)
        for doc in case["documents"]:
            render(doc, classify_rules(doc), d / f"{doc['doc_id']}.pdf")
            n += 1
    print(f"rendered {n} documents to {OUT}")


if __name__ == "__main__":
    main()
