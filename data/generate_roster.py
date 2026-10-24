"""Generate a synthetic health-plan member roster (ALL SYNTHETIC) with plan-side fields and a ground-truth label
'would_lose_paperwork' (member is eligible but would lose coverage for procedural reasons without help).

The label is drawn from a latent probability model with noise and unobserved factors, so the risk scorer
(keeper/risk.py, hand-set points, not fit to these labels) is evaluated on assumed - not real - dynamics.

Calibrated to real public, aggregate data (data/calibration/ma_calibration.json, built by data/fetch_calibration.py):
  - city mix: ACS Medicaid-covered adults 19-64 per city
  - preferred language per city: ACS limited-English-proficiency counts by language
  - share subject to the requirement: MassHealth renewals that needed a form (CMS unwinding renewal outcomes)
  - label base rate among them: MassHealth procedural terminations / renewals that needed a form (same CMS data);
    the latent model's intercept is solved so the expected rate matches it.
Everything else (returned mail, address changes, contact history, exemption hints) is an assumption.

Usage: python data/generate_roster.py  -> data/roster.json
"""
import json
import math
import random
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
AS_OF = date(2026, 10, 24)
CAL = json.loads((ROOT / "calibration" / "ma_calibration.json").read_text(encoding="utf-8"))["roster_params"]
CITY_WEIGHTS = list(CAL["city_weights"].items())
LANGS_BY_CITY = {city: list(p.items()) for city, p in CAL["language_probs_by_city"].items()}
LABEL_NOISE_SD = 0.9
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
    city = pick(rng, CITY_WEIGHTS)
    lang = pick(rng, LANGS_BY_CITY[city])
    c = cases_by_idx.get(i)
    m = {
        "member_id": f"M{i:04d}",
        "name": f"{rng.choice(FIRST[lang])} {chr(65 + rng.randrange(26))}. (synthetic)",
        "age": rng.randint(19, 64),
        "city": city,
        "language": lang,
        "line_of_business": "Medicaid managed care (MassHealth ACO)",
        # state could not verify ex parte; RFI mailed (rate: MassHealth renewals not completed ex parte, CMS)
        "subject_to_requirement": rng.random() < CAL["p_subject_to_requirement"],
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


def latent_z(m):
    """Latent log-odds of procedural loss, before the intercept and noise."""
    due = date.fromisoformat(m["notice_received_date"]) + timedelta(days=30)
    return (1.7 * m["returned_mail"] + 0.8 * m["address_change_90d"] + 0.9 * m["missed_prior_notices"]
            + 0.9 * (m["language"] != m["notice_language"]) + 0.7 * (not m["reached_last_90d"]) + 0.5 * (not m["portal_account"])
            + 0.5 * ((due - AS_OF).days < 14) + 0.6 * (m["exemption_hint"] != "none"))


def solve_intercept(target, n=20000):
    """Intercept that makes the expected label rate among subject members equal the CMS target, on a large
    calibration sample drawn with its own RNG (so the roster's random stream doesn't depend on it)."""
    rng = random.Random(1)
    zs = []
    while len(zs) < n:
        m = member(rng, 0, {})
        if m["subject_to_requirement"]:
            zs.append(latent_z(m) + rng.gauss(0, LABEL_NOISE_SD))
    lo, hi = -10.0, 10.0
    for _ in range(50):
        mid = (lo + hi) / 2
        rate = sum(1 / (1 + math.exp(-(mid + z))) for z in zs) / n
        lo, hi = (mid, hi) if rate < target else (lo, mid)
    return (lo + hi) / 2


def latent_label(rng, m, intercept):
    if not m["subject_to_requirement"]:
        return rng.random() < 0.02  # assumption: renewed ex parte, small chance of a later paperwork loss
    z = intercept + latent_z(m) + rng.gauss(0, LABEL_NOISE_SD)
    return rng.random() < 1 / (1 + math.exp(-z))


def recover_transition_members(cases):
    """20 extra synthetic members for the plan view's Recover and Transition groups (M0201-M0220).

    Kept separate from the calibrated 200 (own RNG, no risk label) so the risk-flag evaluation is unchanged.
    """
    rng = random.Random(4120)
    linked = [c for c in cases if "C47" <= c["case_id"] <= "C54"]
    extra = []
    for i, c in enumerate(linked):
        m = c["member"]
        extra.append({"case_id": c["case_id"], "name": m["name"], "age": m["age"], "language": m["language"],
                      "coverage": m.get("coverage"), "reported_changes": m.get("reported_changes", [])})
    triggers = ["income_above_limit", "turning_65", "postpartum_ending", "moved_out_of_state"]
    for i in range(12 - 0):
        lang = rng.choice(["en", "es", "pt", "ht", "vi", "zh"])
        if i < 7:  # dropped for paperwork, some inside the reconsideration window, some past it
            days = rng.choice([6, 15, 28, 41, 55, 73, 104])
            extra.append({"case_id": None, "name": f"{rng.choice(FIRST[lang])} {chr(65 + rng.randrange(26))}. (synthetic)",
                          "age": rng.randint(19, 64), "language": lang,
                          "coverage": {"status": "terminated_procedural",
                                       "termination_date": (AS_OF - timedelta(days=days)).isoformat(),
                                       "termination_reason": rng.choice(["renewal form not returned", "requested pay stub not received",
                                                                         "request for information not answered"])},
                          "reported_changes": []})
        else:  # likely to lose eligibility
            trig = triggers[i % len(triggers)]
            when = (AS_OF + timedelta(days=rng.randint(10, 45))).isoformat()
            extra.append({"case_id": None, "name": f"{rng.choice(FIRST[lang])} {chr(65 + rng.randrange(26))}. (synthetic)",
                          "age": 64 if trig == "turning_65" else rng.randint(22, 60), "language": lang,
                          "coverage": {"status": "at_risk", "expected_end_date": when},
                          "reported_changes": [{"type": trig, "date": when}]})
    for j, m in enumerate(extra):
        m.update({"member_id": f"M{201 + j:04d}", "city": rng.choice(list(CAL["city_weights"]) if "city_weights" in CAL else ["Boston"]),
                  "group": "recover" if m["coverage"]["status"].startswith("terminated") else "transition",
                  "would_lose_paperwork": None, "subject_to_requirement": True, "notice_received_date": AS_OF.isoformat(),
                  "notice_language": "en", "returned_mail": False, "address_change_90d": False, "missed_prior_notices": 0,
                  "reached_last_90d": rng.random() < 0.5, "has_mobile": True, "sms_opt_in": rng.random() < 0.6, "portal_account": False,
                  "preferred_channel": rng.choice(["sms", "phone"]), "exemption_hint": "none"})
    return extra


def main():
    intercept = solve_intercept(CAL["target_p_lose_given_subject"])
    rng = random.Random(2027)
    cases = sorted((ROOT / "cases").glob("*.json"))
    cases = [json.loads(p.read_text(encoding="utf-8")) for p in cases]
    by_idx = {i + 2: c for i, c in enumerate(cc for cc in cases if cc["case_id"] <= "C45")}
    roster = [member(rng, i, by_idx) for i in range(1, 201)]
    # Maria: illustrative composite, the primary demo member
    maria = next(c for c in cases if c["case_id"] == "C46")
    roster[0].update({"name": maria["member"]["name"], "age": 34, "city": "Lawrence", "language": "es", "notice_language": "en",
                      "subject_to_requirement": True, "notice_received_date": maria["member"]["notice_received_date"],
                      "returned_mail": False, "address_change_90d": True, "missed_prior_notices": 1, "reached_last_90d": False,
                      "has_mobile": True, "sms_opt_in": True, "portal_account": False, "preferred_channel": "phone",
                      "exemption_hint": "caregiver_adult", "case_id": "C46", "conditions_on_file": ["type 2 diabetes"]})
    for m in roster:
        m["would_lose_paperwork"] = latent_label(rng, m, intercept)
    roster[0]["would_lose_paperwork"] = True
    roster += recover_transition_members(cases)
    (ROOT / "roster.json").write_text(json.dumps(roster, indent=1, ensure_ascii=False), encoding="utf-8")
    subject = [m for m in roster if m["subject_to_requirement"] and m.get("group", "at_risk") == "at_risk"]
    print(f"{len(roster)} members, {sum(bool(m['would_lose_paperwork']) for m in roster)} labelled would-lose-for-paperwork; "
          f"{len(subject)} subject to the requirement, {sum(m['would_lose_paperwork'] for m in subject) / len(subject):.1%} of them "
          f"labelled (CMS target {CAL['target_p_lose_given_subject']:.1%}, intercept {intercept:.2f})")


if __name__ == "__main__":
    main()
