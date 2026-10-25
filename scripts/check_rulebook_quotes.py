"""Verify every 'fetched_verbatim' rulebook quote appears verbatim in the downloaded source text, for every pack.

Usage: python scripts/check_rulebook_quotes.py [pack_id ...]
Sources are read from sources_raw/: fr_full.txt (Federal Register full text), shvs.html, and any file a pack's
rules.json names under _meta.sources.<key>.file (eCFR renderer output, PDF text, web pages).
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
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\(\s+", "(", s)  # eCFR markup leaves "( iii )" and "(d)(1) ,"
    return re.sub(r"\s+([,.;:)])", r"\1", s).strip()


def page_text(t):
    t = re.sub(r"(?s)<script.*?</script>|<style.*?</style>", "", t)
    return norm(html.unescape(re.sub(r"<[^>]+>", " ", t)))


def load_sources(rb):
    src = {}
    fr = ROOT / "sources_raw" / "fr_full.txt"
    if fr.exists():
        src["FR"] = norm(fr.read_bytes().decode("utf-8", "ignore"))
    sh = ROOT / "sources_raw" / "shvs.html"
    if sh.exists():
        src["SHVS"] = page_text(sh.read_text(encoding="utf-8", errors="ignore"))
    for key, meta in rb["_meta"]["sources"].items():
        f = ROOT / "sources_raw" / meta.get("file", "")
        if meta.get("file") and f.exists():
            src[key] = page_text(f.read_text(encoding="utf-8", errors="ignore"))
    return src


def check(pack_dir):
    rb = json.loads((pack_dir / "rules.json").read_text(encoding="utf-8"))
    src = load_sources(rb)
    bad = 0
    print(f"== {pack_dir.name}")
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
    return bad


def main():
    wanted = set(sys.argv[1:])
    packs = [d for d in sorted((ROOT / "packs").iterdir()) if (d / "rules.json").exists() and (not wanted or d.name in wanted)]
    bad = sum(check(d) for d in packs)
    print(f"\n{bad} problem(s)")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
