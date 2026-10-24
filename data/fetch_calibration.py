"""Fetch REAL public, aggregate data and derive the parameters the synthetic roster is calibrated to.

No member-level data is used or produced: every input is a published state- or area-level count.

Sources (no API key needed):
  - CMS, "Medicaid and CHIP Updated Renewal Outcomes" (unwinding renewals due Mar 2023 - Mar 2024), Massachusetts rows:
    share of renewals that needed a form (not renewed ex parte) and share of those ending in a procedural termination.
  - US Census Bureau, ACS 2020-2024 5-year table-based summary file:
      C16001  language spoken at home x English ability, by city (place)
      B16001  detailed languages x English ability, by PUMA (B16001 isn't published for places; used only to split
              C16001's collapsed groups into Haitian and Portuguese)
      C27007  Medicaid/means-tested public coverage by sex by age, by city (adults 19-64 -> city weights)

Raw downloads (filtered to the needed rows) are saved in sources_raw/calibration/ (git-ignored).
Output: data/calibration/ma_calibration.json (committed, so generate_roster.py runs offline).

Usage: python data/fetch_calibration.py [--refresh]
"""
import csv
import io
import json
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW = ROOT.parent / "sources_raw" / "calibration"
OUT = ROOT / "calibration" / "ma_calibration.json"

CMS_URL = "https://download.medicaid.gov/data/updated-renewal-outcomes-october-2024-releasefinal.csv"
CMS_PAGE = "https://data.medicaid.gov/dataset/e6205a51-e6d7-4849-9882-4483b8a28c41"
ACS_URL = "https://www2.census.gov/programs-surveys/acs/summary_file/2024/table-based-SF/data/5YRData/acsdt5y2024-{}.dat"
ACS_PAGE = "https://www.census.gov/programs-surveys/acs/data/summary-file.html"

# City -> Census place GEO_ID and the 2020 PUMA(s) that best cover it (PUMA names from the ACS geography file).
CITIES = {
    "Boston": ("1600000US2507000", ["795P200US2500801", "795P200US2500802", "795P200US2500803", "795P200US2500804",
                                    "795P200US2500805"], "Boston City PUMAs 00801-00805"),
    "Worcester": ("1600000US2582000", ["795P200US2500504", "795P200US2500505"], "Worcester City (East) + (West) PUMAs"),
    "Springfield": ("1600000US2567000", ["795P200US2500402"], "Hampden County (Central)--Springfield PUMA"),
    "Lowell": ("1600000US2537000", ["795P200US2500602"], "Middlesex County--Lowell PUMA"),
    "Brockton": ("1600000US2509000", ["795P200US2501101"], "Plymouth County--Brockton PUMA"),
    "Lynn": ("1600000US2537490", ["795P200US2500705"], "Essex County--Lynn & Nahant PUMA"),
    "New Bedford": ("1600000US2545000", ["795P200US2501004"], "Bristol County (South)--New Bedford, Dartmouth & Westport PUMA"),
    "Fall River": ("1600000US2523000", ["795P200US2501003"], "Bristol County (Central)--Fall River, Somerset & Acushnet PUMA"),
    "Lawrence": ("1600000US2534550", ["795P200US2500702"], "Essex County (West)--Lawrence & Andover PUMA"),
    "Chelsea": ("1600000US2513205", ["795P200US2500806"], "Suffolk County (North)--Revere, Chelsea & Winthrop PUMA"),
}

# ACS cell numbers. Each language group is (total, speak English "very well", speak English less than "very well").
C16001_GROUPS = {"Spanish": 3, "French, Haitian, or Cajun": 6, "German or other West Germanic": 9,
                 "Russian, Polish, or other Slavic": 12, "Other Indo-European": 15, "Korean": 18, "Chinese": 21,
                 "Vietnamese": 24, "Tagalog": 27, "Other Asian and Pacific Island": 30, "Arabic": 33, "Other and unspecified": 36}
B16001_GROUPS = {"Spanish": 3, "French": 6, "Haitian": 9, "Italian": 12, "Portuguese": 15, "German": 18, "Yiddish/West Germanic": 21,
                 "Greek": 24, "Russian": 27, "Polish": 30, "Serbo-Croatian": 33, "Ukrainian/other Slavic": 36, "Armenian": 39,
                 "Persian": 42, "Gujarati": 45, "Hindi": 48, "Urdu": 51, "Punjabi": 54, "Bengali": 57, "Nepali/other Indic": 60,
                 "Other Indo-European": 63, "Telugu": 66, "Tamil": 69, "Malayalam/other Dravidian": 72, "Chinese": 75, "Japanese": 78,
                 "Korean": 81, "Hmong": 84, "Vietnamese": 87, "Khmer": 90, "Thai/Lao/Tai-Kadai": 93, "Other Asian": 96, "Tagalog": 99,
                 "Other Austronesian": 102, "Arabic": 105, "Hebrew": 108, "Amharic/Somali/Afro-Asiatic": 111, "West African": 114,
                 "Central/East/Southern African": 117, "Navajo": 120, "Other Native North American": 123, "Other and unspecified": 126}
# B16001 languages that C16001 collapses into "Other Indo-European languages".
OTHER_IE = ["Italian", "Portuguese", "Greek", "Armenian", "Persian", "Gujarati", "Hindi", "Urdu", "Punjabi", "Bengali",
            "Nepali/other Indic", "Other Indo-European"]
# Roster languages (the six the tool supports) -> how each is read from ACS.
SUPPORTED = {"es": "Spanish", "pt": "Portuguese", "ht": "Haitian", "vi": "Vietnamese", "zh": "Chinese"}


def _get(url):
    print("  downloading", url)
    req = urllib.request.Request(url, headers={"User-Agent": "coverage-keeper-calibration/1.0"})
    return urllib.request.urlopen(req, timeout=300)


def acs_rows(table, geoids, refresh):
    """Rows of an ACS table for the given GEO_IDs, as {geoid: {cell_number: value}}. Streams the national file once."""
    path = RAW / f"acsdt5y2024-{table}.ma.dat"
    if refresh or not path.exists():
        RAW.mkdir(parents=True, exist_ok=True)
        keep = []
        with _get(ACS_URL.format(table)) as r:
            for i, line in enumerate(io.TextIOWrapper(r, encoding="utf-8")):
                if i == 0 or line.split("|", 1)[0] in geoids:
                    keep.append(line)
        path.write_text("".join(keep), encoding="utf-8")
    lines = path.read_text(encoding="utf-8").splitlines()
    head = lines[0].split("|")
    out = {}
    for line in lines[1:]:
        vals = line.split("|")
        cells = {}
        for h, v in zip(head[1:], vals[1:]):
            m = re.match(r".*_E(\d+)$", h)
            if m:
                cells[int(m.group(1))] = float(v) if v not in ("", "null") else 0.0
        out[vals[0]] = cells
    missing = set(geoids) - set(out)
    if missing:
        sys.exit(f"{table}: no rows for {sorted(missing)} (re-run with --refresh?)")
    return out


def cms_massachusetts(refresh):
    path = RAW / "updated-renewal-outcomes.csv"
    if refresh or not path.exists():
        RAW.mkdir(parents=True, exist_ok=True)
        with _get(CMS_URL) as r:
            path.write_bytes(r.read())
    keys = {"5": "due", "5a1": "renewed_ex_parte", "5a2": "renewed_via_form", "5b": "ineligible_via_form",
            "5c": "procedural_terminations", "5d": "pending"}
    months = {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            row = {k.strip(): (v or "").strip() for k, v in row.items()}
            if row["State"] != "MA" or row["Data Type"] != "Updated" or not row["Metric name"].startswith("Total"):
                continue
            m = re.search(r"\(Metric (\w+)\)\s*$", row["Metric name"])
            if m and m.group(1) in keys:
                months.setdefault(row["Reporting period"], {})[keys[m.group(1)]] = float(row["Value"] or 0)
    months = {p: v for p, v in sorted(months.items()) if v.get("due")}
    tot = {k: sum(v.get(k, 0) for v in months.values()) for k in keys.values()}
    form = tot["due"] - tot["renewed_ex_parte"]
    monthly = [{"reporting_period": p, "due": int(v["due"]),
                "procedural_share_of_form_renewals": round(v["procedural_terminations"] / (v["due"] - v["renewed_ex_parte"]), 4)}
               for p, v in months.items()]
    return {
        "dataset": "Medicaid and CHIP Updated Renewal Outcomes (data type 'Updated': pending renewals resolved 3 months after due)",
        "state": "MA", "reporting_periods": [min(months), max(months)], "months": len(months),
        "totals": {k: int(v) for k, v in tot.items()},
        "derived": {
            "ex_parte_share": round(tot["renewed_ex_parte"] / tot["due"], 4),
            "form_needed_share": round(form / tot["due"], 4),
            "procedural_share_of_form_renewals": round(tot["procedural_terminations"] / form, 4),
            "procedural_share_of_due": round(tot["procedural_terminations"] / tot["due"], 4),
            "procedural_share_of_terminations": round(tot["procedural_terminations"]
                                                      / (tot["procedural_terminations"] + tot["ineligible_via_form"]), 4),
        },
        "monthly": monthly,
    }


def lep(cells, base):
    return cells[base + 2]


def city_language(name, place, pumas):
    """Language mix for one city. City-level C16001 counts; PUMA-level B16001 splits the collapsed groups."""
    c = place
    b = {k: sum(p[v + 2] for p in pumas) for k, v in B16001_GROUPS.items()}  # LEP counts summed over the city's PUMAs
    ht_ratio = b["Haitian"] / (b["Haitian"] + b["French"]) if b["Haitian"] + b["French"] else 0.0
    other_ie = sum(b[k] for k in OTHER_IE)
    pt_ratio = b["Portuguese"] / other_ie if other_ie else 0.0
    lep_counts = {
        "es": lep(c, C16001_GROUPS["Spanish"]),
        "pt": lep(c, C16001_GROUPS["Other Indo-European"]) * pt_ratio,
        "ht": lep(c, C16001_GROUPS["French, Haitian, or Cajun"]) * ht_ratio,
        "vi": lep(c, C16001_GROUPS["Vietnamese"]),
        "zh": lep(c, C16001_GROUPS["Chinese"]),
    }
    very_well = sum(c[v + 1] for v in C16001_GROUPS.values())
    all_lep = sum(lep(c, v) for v in C16001_GROUPS.values())
    en = c[2] + very_well
    unsupported = all_lep - sum(lep_counts.values())
    denom = en + sum(lep_counts.values())
    probs = {"en": en / denom}
    probs.update({k: v / denom for k, v in lep_counts.items()})
    # Biggest LEP languages the tool does not support yet (PUMA-level detail).
    pb = {k: v for k, v in b.items() if k not in SUPPORTED.values()}
    b_lep = sum(b.values())
    top = sorted(pb.items(), key=lambda kv: -kv[1])[:3]
    return {
        "pop_5plus": int(c[1]), "lep_share": round(all_lep / c[1], 4),
        "lep_counts": {k: int(round(v)) for k, v in lep_counts.items()},
        "split_ratios_from_puma": {"haitian_of_french_haitian_cajun_lep": round(ht_ratio, 4),
                                   "portuguese_of_other_indo_european_lep": round(pt_ratio, 4)},
        "unsupported_lep_share_of_pop": round(unsupported / c[1], 4),
        "top_unsupported_lep_languages_puma": [{"language": k, "share_of_lep": round(v / b_lep, 4)} for k, v in top if v],
        "roster_language_probs": {k: round(v, 4) for k, v in probs.items()},
    }


def check_collapse(c16, b16, pumas):
    """Sanity check on the language mapping: at PUMA level, B16001 details must add up to C16001's collapsed groups."""
    worst = 0.0
    for g in pumas:
        for group, parts in (("Other Indo-European", OTHER_IE), ("French, Haitian, or Cajun", ["French", "Haitian"])):
            want = lep(c16[g], C16001_GROUPS[group])
            got = sum(lep(b16[g], B16001_GROUPS[p]) for p in parts)
            worst = max(worst, abs(want - got) / max(want, 1))
    return worst


def main():
    refresh = "--refresh" in sys.argv
    places = [v[0] for v in CITIES.values()]
    pumas = [p for v in CITIES.values() for p in v[1]]
    print("CMS renewal outcomes (Massachusetts)")
    cms = cms_massachusetts(refresh)
    print("ACS 2020-2024 5-year tables")
    c16 = acs_rows("c16001", set(places + pumas), refresh)
    b16 = acs_rows("b16001", set(pumas), refresh)
    c27 = acs_rows("c27007", set(places), refresh)
    err = check_collapse(c16, b16, pumas)
    if err > 0.01:
        sys.exit(f"B16001 details don't add up to C16001 groups (max relative error {err:.1%}); language mapping is off")

    cities = {}
    for name, (place, pz, puma_label) in CITIES.items():
        med = c27[place][7] + c27[place][17]
        adults = c27[place][6] + c27[place][16]
        cities[name] = {"place_geoid": place, "pumas": pz, "puma_note": puma_label,
                        "medicaid_adults_19_64": int(med), "medicaid_share_of_adults_19_64": round(med / adults, 4)}
        cities[name].update(city_language(name, c16[place], [b16[p] for p in pz]))
    total_med = sum(c["medicaid_adults_19_64"] for c in cities.values())
    d = cms["derived"]
    out = {
        "_meta": {
            "generated_by": "data/fetch_calibration.py", "retrieved": date.today().isoformat(),
            "note": "Real, public, aggregate data only (state- and area-level counts). The roster built from these "
                    "parameters is still entirely synthetic; no real member appears in it.",
            "sources": [
                {"id": "CMS_RENEWALS", "title": "CMS, Medicaid and CHIP Updated Renewal Outcomes (Unwinding Data Report, Oct 2024 release)",
                 "url": CMS_PAGE, "file": CMS_URL},
                {"id": "ACS_C16001", "title": "US Census Bureau, ACS 2020-2024 5-year, C16001 Language Spoken at Home by Ability to Speak English (places)",
                 "url": ACS_PAGE, "file": ACS_URL.format("c16001")},
                {"id": "ACS_B16001", "title": "US Census Bureau, ACS 2020-2024 5-year, B16001 detailed languages (PUMAs; splits Haitian and Portuguese)",
                 "url": ACS_PAGE, "file": ACS_URL.format("b16001")},
                {"id": "ACS_C27007", "title": "US Census Bureau, ACS 2020-2024 5-year, C27007 Medicaid/Means-Tested Public Coverage by Sex by Age (places)",
                 "url": ACS_PAGE, "file": ACS_URL.format("c27007")},
            ],
            "method": [
                "Preferred roster language = a non-English language only for residents who speak English less than 'very well' "
                "(limited English proficiency, LEP); everyone else (English-only, or bilingual 'very well') is 'en'.",
                "es, zh, vi come straight from C16001 at city level. ht and pt are C16001's collapsed groups ('French, Haitian, or "
                "Cajun'; 'Other Indo-European') times the Haitian / Portuguese share of that group in the city's PUMA(s) from B16001.",
                "LEP residents who speak a language the tool doesn't support yet are left out of the roster mix and reported "
                "per city as unsupported_lep_share_of_pop.",
                "City weights = Medicaid/means-tested public coverage among adults 19-64 (C27007).",
                "p_subject_to_requirement = MassHealth's share of renewals NOT completed ex parte (a form was needed).",
                "target_p_lose_given_subject = procedural terminations / renewals that needed a form; the generator solves "
                "the latent model's intercept so the expected label rate among subject members matches it.",
            ],
            "caveats": [
                "Unwinding renewals (2023-24) are a proxy for the 2027 community-engagement verification, not the same process.",
                "Procedural terminations include some people who were in fact ineligible, and some who were reinstated later; "
                "CMS data can't separate them, so the label rate is an upper-bound proxy for 'eligible but lost to paperwork'.",
                "ACS language and English ability cover all residents 5+, not MassHealth members specifically; Medicaid adults "
                "are likely more often LEP, so the language mismatch rate is probably conservative.",
                "PUMAs used for the Haitian/Portuguese split include neighbouring towns for Lawrence (Andover), Chelsea "
                "(Revere, Winthrop), New Bedford and Fall River. ACS estimates for small groups carry wide margins of error.",
            ],
        },
        "cms_renewals_ma": cms,
        "acs_cities": cities,
        "roster_params": {
            "city_weights": {k: round(v["medicaid_adults_19_64"] / total_med, 4) for k, v in cities.items()},
            "language_probs_by_city": {k: v["roster_language_probs"] for k, v in cities.items()},
            "p_subject_to_requirement": d["form_needed_share"],
            "target_p_lose_given_subject": d["procedural_share_of_form_renewals"],
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"MA renewals {cms['reporting_periods'][0]}-{cms['reporting_periods'][1]}: {cms['totals']['due']:,} due; "
          f"{d['form_needed_share']:.1%} needed a form; {d['procedural_share_of_form_renewals']:.1%} of those ended procedurally "
          f"({d['procedural_share_of_terminations']:.1%} of all terminations)")
    for k, v in cities.items():
        mix = ", ".join(f"{l} {p:.0%}" for l, p in v["roster_language_probs"].items() if p >= 0.005)
        print(f"  {k:12s} weight {out['roster_params']['city_weights'][k]:.1%}  {mix}  (unsupported LEP {v['unsupported_lep_share_of_pop']:.1%})")
    print("wrote", OUT.relative_to(ROOT.parent))


if __name__ == "__main__":
    main()
