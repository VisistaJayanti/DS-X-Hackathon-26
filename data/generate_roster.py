"""Generate a synthetic health-plan member roster (ALL SYNTHETIC) with plan-side fields and a ground-truth label
'would_lose_paperwork' (member is eligible but would lose coverage for procedural reasons without help).

The label is drawn from a latent probability model with noise and unobserved factors, so the risk scorer
(keeper/risk.py, hand-set points, not fit to these labels) is evaluated on assumed - not real - dynamics.

Usage: python data/generate_roster.py  -> data/roster.json
"""
import json
import math
import random
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
AS_OF = date(2026, 10, 24)
CITIES = ["Lawrence", "Boston", "Springfield", "Lynn", "Worcester", "Chelsea", "Lowell", "Brockton", "New Bedford", "Fall River"]
LANGS = [("en", 0.52), ("es", 0.26), ("pt", 0.07), ("ht", 0.06), ("vi", 0.045), ("zh", 0.045)]
FIRST = {"en": ["James", "Ashley", "Tyler", "Brittany", "Kevin", "Nicole"], "es": ["Maria", "Jose", "Luz", "Carlos", "Yesenia", "Luis"],
         "pt": ["Joana", "Paulo", "Ana", "Thiago"], "ht": ["Jean", "Marie", "Widline", "Fritz"], "vi": ["Hoa", "Minh", "Thanh", "Lan"],
         "zh": ["Wei", "Mei", "Jun", "Li"]}
HINTS = ["none", "none", "none", "caregiver_adult", "caregiver_child", "chronic_condition", "behavioral_health", "student"]


def pick(rng, weighted):
    r, acc = rng.random(), 0
    for v, w in weighted:
        acc += w
        if r < acc:
            return v
    return weighted[-1][0]


def member(rng, i, cases_by_idx):
    lang = pick(rng, LANGS)
    c = cases_by_idx.get(i)
    m = {
        "member_id": f"M{i:04d}",
        "name": f"{rng.choice(FIRST[lang])} {chr(65 + rng.randrange(26))}. (synthetic)",
        "age": rng.randint(19, 64),
        "city": rng.choice(CITIES),
        "language": lang,
        "line_of_business": "Medicaid managed care (MassHealth ACO)",
        "subject_to_requirement": rng.random() < 0.8,  # state could not verify ex parte; RFI mailed
        "notice_received_date": (AS_OF - timedelta(days=rng.randint(2, 26))).isoformat(),
        "notice_language": "en",
        "returned_mail": rng.random() < 0.09,
        "address_change_90d": rng.random() < 0.13,
        "missed_prior_notices": pick(rng, [(0, 0.65), (1, 0.25), (2, 0.10)]),
        "reached_last_90d": rng.random() < 0.55,
        "contact_attempts_30d": rng.randint(0, 3),
        "has_mobile": rng.random() < 0.85,
        "sms_opt_in": rng.random() < 0.6,
        "portal_account": rng.random() < 0.35,
        "preferred_channel": pick(rng, [("sms", 0.45), ("phone", 0.35), ("mail", 0.12), ("in_person", 0.08)]),
        "exemption_hint": rng.choice(HINTS),  # from claims/care-management data; never used to deny anything
        "case_id": None,
    }
    if c:
        m.update({"name": c["member"]["name"], "age": c["member"]["age"], "language": c["member"]["language"],
                  "notice_received_date": c["member"]["notice_received_date"], "case_id": c["case_id"]})
    m["sms_opt_in"] = m["sms_opt_in"] and m["has_mobile"]
    return m


def latent_label(rng, m):
    if not m["subject_to_requirement"]:
        return rng.random() < 0.02
    due = date.fromisoformat(m["notice_received_date"]) + timedelta(days=30)
    z = (-2.4 + 1.7 * m["returned_mail"] + 0.8 * m["address_change_90d"] + 0.9 * m["missed_prior_notices"]
         + 0.9 * (m["language"] != m["notice_language"]) + 0.7 * (not m["reached_last_90d"]) + 0.5 * (not m["portal_account"])
         + 0.5 * ((due - AS_OF).days < 14) + 0.6 * (m["exemption_hint"] != "none") + rng.gauss(0, 0.9))
    return rng.random() < 1 / (1 + math.exp(-z))


def main():
    rng = random.Random(2027)
    cases = sorted((ROOT / "cases").glob("*.json"))
    cases = [json.loads(p.read_text(encoding="utf-8")) for p in cases]
    by_idx = {i + 2: c for i, c in enumerate(cc for cc in cases if cc["case_id"] != "C46")}
    roster = [member(rng, i, by_idx) for i in range(1, 201)]
    # Maria: illustrative composite, the primary demo member
    maria = next(c for c in cases if c["case_id"] == "C46")
    roster[0].update({"name": maria["member"]["name"], "age": 34, "city": "Lawrence", "language": "es", "notice_language": "en",
                      "subject_to_requirement": True, "notice_received_date": maria["member"]["notice_received_date"],
                      "returned_mail": False, "address_change_90d": True, "missed_prior_notices": 1, "reached_last_90d": False,
                      "has_mobile": True, "sms_opt_in": True, "portal_account": False, "preferred_channel": "phone",
                      "exemption_hint": "caregiver_adult", "case_id": "C46", "conditions_on_file": ["type 2 diabetes"]})
    for m in roster:
        m["would_lose_paperwork"] = latent_label(rng, m)
    roster[0]["would_lose_paperwork"] = True
    (ROOT / "roster.json").write_text(json.dumps(roster, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{len(roster)} members, {sum(m['would_lose_paperwork'] for m in roster)} labelled would-lose-for-paperwork")


if __name__ == "__main__":
    main()
