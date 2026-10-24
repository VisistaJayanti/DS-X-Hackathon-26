"""Date / money / language helpers shared by the deterministic engines."""
import re
from datetime import date

MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3, "april": 4, "apr": 4, "may": 5,
    "june": 6, "jun": 6, "july": 7, "jul": 7, "august": 8, "aug": 8, "september": 9, "sept": 9, "sep": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
    # Spanish / Portuguese
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
    "janeiro": 1, "fevereiro": 2, "março": 3, "maio": 5, "junho": 6, "julho": 7, "setembro": 9,
    "outubro": 10, "novembro": 11, "dezembro": 12,
}
_MON = "|".join(sorted(MONTHS, key=len, reverse=True))

RE_NUMERIC = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b")
RE_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
RE_LONG = re.compile(rf"\b({_MON})\.?\s+(\d{{1,2}}),?\s+(\d{{4}})\b", re.I)
RE_ROMANCE = re.compile(rf"\b(\d{{1,2}})\s+de\s+({_MON})\s+de\s+(\d{{4}})\b", re.I)
RE_MONTH_YEAR = re.compile(rf"\b({_MON})\.?\s+(?:de\s+)?(\d{{4}})\b", re.I)


def _safe(y, m, d):
    try:
        return date(int(y), int(m), int(d))
    except ValueError:
        return None


def find_dates(s):
    out = []
    for m in RE_ISO.finditer(s):
        out.append((m.start(), _safe(m.group(1), m.group(2), m.group(3))))
    for m in RE_NUMERIC.finditer(s):
        out.append((m.start(), _safe(m.group(3), m.group(1), m.group(2))))
    for m in RE_LONG.finditer(s):
        out.append((m.start(), _safe(m.group(3), MONTHS[m.group(1).lower()], m.group(2))))
    for m in RE_ROMANCE.finditer(s):
        out.append((m.start(), _safe(m.group(3), MONTHS[m.group(2).lower()], m.group(1))))
    return [d for _, d in sorted(out, key=lambda x: x[0]) if d]


def first_date(s):
    d = find_dates(s)
    return d[0] if d else None


def find_month(s):
    """'September 2026' / 'setembro de 2026' / '09/2026' -> '2026-09'."""
    m = RE_MONTH_YEAR.search(s)
    if m:
        return f"{m.group(2)}-{MONTHS[m.group(1).lower()]:02d}"
    d = first_date(s)
    return f"{d.year}-{d.month:02d}" if d else None


def money(s):
    m = re.search(r"\$\s?([\d,]+(?:\.\d{2})?)", s)
    return float(m.group(1).replace(",", "")) if m else None


def age_on(dob, on):
    return on.year - dob.year - ((on.month, on.day) < (dob.month, dob.day))


def add_months(d, n):
    y, m = divmod(d.month - 1 + n, 12)
    import calendar

    day = min(d.day, calendar.monthrange(d.year + y, m + 1)[1])
    return date(d.year + y, m + 1, day)


ES_WORDS = {"paciente", "atentamente", "trabajar", "condición", "corresponda", "fecha", "su", "tiene", "le", "yo", "vivo", "con", "mi", "madre", "desde", "los", "días", "firma", "ayudo"}
PT_WORDS = {"declaramos", "trabalha", "empresa", "horas", "em", "nossa", "um", "trabalhou", "declaração"}


def guess_language(text):
    words = set(re.findall(r"[a-záéíóúãõçñ]+", text.lower()))
    es, pt = len(words & ES_WORDS), len(words & PT_WORDS)
    if max(es, pt) < 3:
        return "en"
    return "es" if es >= pt else "pt"
