"""Verify every 'fetched_verbatim' rulebook quote appears verbatim in the downloaded source text.

Usage: python scripts/check_rulebook_quotes.py
Requires sources_raw/fr_full.txt (Federal Register full text) and sources_raw/shvs.html.
"""
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def norm(s):
    s = s.replace("\x00", "")
    s = re.sub(r"\[\[Page \d+\]\]", " ", s)
    s = s.replace("``", '"').replace("''", '"').replace("’", "'")
    s = re.sub(r"-\s*\n\s*", "-", s)  # hyphenated line breaks
    return re.sub(r"\s+", " ", s).strip()


def load_sources():
    src = {}
    fr = ROOT / "sources_raw" / "fr_full.txt"
    if fr.exists():
        src["FR"] = norm(fr.read_bytes().decode("utf-8", "ignore"))
    sh = ROOT / "sources_raw" / "shvs.html"
    if sh.exists():
        t = sh.read_text(encoding="utf-8", errors="ignore")
        t = re.sub(r"(?s)<script.*?</script>|<style.*?</style>", "", t)
        src["SHVS"] = norm(html.unescape(re.sub(r"<[^>]+>", " ", t)))
    return src


def main():
    rb = json.loads((ROOT / "packs" / "masshealth_ce_2027" / "rules.json").read_text(encoding="utf-8"))
    src = load_sources()
    bad = 0
    for r in rb["rules"]:
        if r["source_status"] != "fetched_verbatim":
            print(f"SKIP  {r['id']:<22} ({r['source_status']})")
            continue
        text = src.get(r["source"])
        if text is None:
            print(f"MISS  {r['id']:<22} source file for {r['source']} not downloaded")
            bad += 1
            continue
        for key in ("quote", "quote_2"):
            if key in r:
                ok = norm(r[key]) in text
                bad += not ok
                print(f"{'OK  ' if ok else 'FAIL'}  {r['id']:<22} {key}")
    print(f"\n{bad} problem(s)")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
