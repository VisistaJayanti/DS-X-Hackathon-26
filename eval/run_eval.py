"""Coverage Keeper evaluation. One command:  python eval/run_eval.py  [--llm] [--split test|dev|all]

Runs the pipeline on every synthetic case and reports:
  - pathway accuracy (top-1, top-2), evidence-sufficiency accuracy
  - missing-evidence (gap) precision / recall, micro-averaged over labelled gap codes
  - unsupported-claim rate in generated outputs WITHOUT vs WITH the verifier (ablation)
  - latency and cost per case
  - fairness breakdowns by member language and case type
  - risk-flag precision / recall at top-k on the 200-member roster
Writes eval/results.json (shown in the UI) and eval/RESULTS.md.

--llm runs the LLM engines (needs an API key for each provider in config.MODELS, or a filled cache in replay
mode). Responses are cached, so re-runs are fast and free, and a run interrupted by a free tier's daily quota
resumes where it stopped. Without --llm only the deterministic baseline runs.
"""
import argparse
import json
import os
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from keeper import config, pipeline, risk, rulebook  # noqa: E402
from keeper.llm import LLMUnavailable  # noqa: E402
from keeper.stages import verify  # noqa: E402

CASE_TYPE = {
    "EX_MEDICALLY_FRAIL": "medical frailty", "EX_SUD_TREATMENT": "medical frailty", "EX_CAREGIVER_CHILD": "caregiving",
    "EX_CAREGIVER_DISABLED": "caregiving", "EX_PREGNANT_POSTPARTUM": "pregnancy/postpartum", "EDUCATION": "education",
    "COMBINATION": "education", "WORK_80": "work/income", "INCOME_580": "work/income", "NONE": "no pathway",
    "OUT_OF_SCOPE_AGE": "out of scope", "OUT_OF_SCOPE_MEDICARE": "out of scope",
}


def case_type(c):
    return CASE_TYPE.get(c["labels"]["correct_pathways"][0], "other exemption")


def all_claims(trace, which):
    """Claims from the raw draft ('raw') or the verified output ('verified')."""
    st = {s["key"]: s["output"] for s in trace["stages"]}
    src = st["draft"] if which == "raw" or "verify" not in st else st["verify"]["verified"]
    out = [c for s in src["packet"]["sections"] for c in s["claims"]]
    if src.get("request"):
        out += src["request"]["claims"]
    out += src["member_en"]
    return [c for c in out if c.get("kind") != "boilerplate"]


def judge(case, trace, claims, use_llm, meter):
    """Independent judge: deterministic grounding checks, plus (LLM runs) an entailment check by a different, stronger model."""
    st = {s["key"]: s["output"] for s in trace["stages"]}
    ctx = verify.context(case, st["extract"], st["rules"], st["gaps"], st.get("outcome"))
    bad = {c["claim_id"] for c in claims if verify.check_claim(c, ctx)}
    if use_llm and claims:
        try:
            verdicts = verify.entail(claims, ctx, meter, stage="judge")
            bad |= {cid for cid, v in verdicts.items() if v["verdict"] == "unsupported"}
        except LLMUnavailable:
            pass
    return len(bad), len(claims)


RETAIN_SENTENCES = ("you may qualify through", "your documents look complete", "the new work rules may not apply")


def told_still_eligible(trace):
    """A transition case must not be told it can keep coverage the usual way (retain framing or a ready packet)."""
    fin = trace["final"]
    text = " ".join(s["en"] for s in fin["member"]["sentences"]).lower()
    return any(k in text for k in RETAIN_SENTENCES) or fin["packet"].get("status") not in (None, "none")


def score_case(c, trace):
    lab, s = c["labels"], trace["summary"]
    want_oc = lab.get("outcome", "retain")
    ranking = s["ranking"]
    want, got_gaps = set(lab["gaps"]), set(s["gaps"])
    return {
        "case_id": c["case_id"], "title": c["title"], "split": c["split"], "language": c["member"].get("language", "en"),
        "case_type": case_type(c), "top1": ranking[0] in lab["correct_pathways"],
        "top2": any(p in lab["correct_pathways"] for p in ranking[:2]),
        "sufficiency": s["evidence_sufficient"] == lab["evidence_sufficient"],
        "tp": len(want & got_gaps), "fp": len(got_gaps - want), "fn": len(want - got_gaps),
        "latency_ms": s["latency_ms"], "cost": s["cost_usd"], "ranking": ranking[:3], "gaps": sorted(got_gaps), "want_gaps": sorted(want),
        "want": lab["correct_pathways"],
        "outcome": s.get("outcome"), "want_outcome": want_oc, "outcome_ok": s.get("outcome") == want_oc,
        "key_date_ok": (s.get("key_date") == lab["key_date"]) if lab.get("key_date") else None,
        "told_eligible": told_still_eligible(trace) if want_oc == "transition" else None,
        # The costlier error in the other direction: someone who can keep coverage is routed to new coverage.
        "told_to_move": (s.get("outcome") == "transition") if want_oc != "transition" else None,
    }


def aggregate(rows):
    n = len(rows)
    tp, fp, fn = (sum(r[k] for r in rows) for k in ("tp", "fp", "fn"))
    return {
        "n": n, "top1": sum(r["top1"] for r in rows) / n, "top2": sum(r["top2"] for r in rows) / n,
        "sufficiency_acc": sum(r["sufficiency"] for r in rows) / n,
        "gap_precision": tp / (tp + fp) if tp + fp else 1.0, "gap_recall": tp / (tp + fn) if tp + fn else 1.0,
        "latency_ms_mean": round(sum(r["latency_ms"] for r in rows) / n), "cost_usd_mean": sum(r["cost"] for r in rows) / n,
        **outcome_metrics(rows),
    }


def outcome_metrics(rows):
    keyed = [r for r in rows if r.get("key_date_ok") is not None]
    trans = [r for r in rows if r.get("told_eligible") is not None]
    stay = [r for r in rows if r.get("told_to_move") is not None]
    return {"outcome_acc": sum(r["outcome_ok"] for r in rows) / len(rows) if rows else None,
            "key_date_acc": sum(r["key_date_ok"] for r in keyed) / len(keyed) if keyed else None, "key_date_n": len(keyed),
            "transition_told_eligible_rate": sum(r["told_eligible"] for r in trans) / len(trans) if trans else None,
            "transition_n": len(trans),
            "eligible_told_to_move_rate": sum(r["told_to_move"] for r in stay) / len(stay) if stay else None, "eligible_n": len(stay)}


def run_engine(cases, name, use_llm, split):
    rows, uns_raw, uns_ver, n_raw, n_ver, judge_meter = [], 0, 0, 0, 0, []
    for c in cases:
        t0 = time.time()
        trace = pipeline.run(c, use_llm=use_llm, use_verifier=True)
        trace["summary"]["latency_ms"] = trace["summary"]["latency_ms"] or int((time.time() - t0) * 1000)
        rows.append(score_case(c, trace))
        b, n = judge(c, trace, all_claims(trace, "raw"), use_llm, judge_meter)
        uns_raw, n_raw = uns_raw + b, n_raw + n
        b, n = judge(c, trace, all_claims(trace, "verified"), use_llm, judge_meter)
        uns_ver, n_ver = uns_ver + b, n_ver + n
        print(f"  {name:<14} {c['case_id']} top1={'Y' if rows[-1]['top1'] else 'n'} gaps={rows[-1]['gaps']}", flush=True)
    sel = [r for r in rows if split == "all" or r["split"] == split]
    base = dict(aggregate(sel), split=split)
    return rows, [
        dict(base, name=f"{name} - verifier OFF", unsupported=uns_raw, claims=n_raw, unsupported_rate=uns_raw / n_raw if n_raw else None),
        dict(base, name=f"{name} - verifier ON", unsupported=uns_ver, claims=n_ver, unsupported_rate=uns_ver / n_ver if n_ver else None),
    ], sum(m["cost"] for m in judge_meter)


def fairness(rows):
    out = {}
    for dim in ("language", "case_type", "want_outcome"):
        groups = defaultdict(list)
        for r in rows:
            groups[r[dim]].append(r)
        out[dim] = [dict(group=g, **{k: v for k, v in aggregate(rs).items() if k in ("n", "top1", "gap_recall", "gap_precision")})
                    for g, rs in sorted(groups.items())]
    return out


def risk_eval(ks=(20, 40, 60)):
    roster = [m for m in json.loads((ROOT / "data" / "roster.json").read_text(encoding="utf-8")) if m.get("group", "at_risk") == "at_risk"]
    pos = {m["member_id"] for m in roster if m["would_lose_paperwork"]}
    ranked = [s["member"]["member_id"] for s in risk.rank_roster(roster)]
    by_deadline = [m["member_id"] for m in sorted(roster, key=lambda m: m["notice_received_date"])]
    rng = random.Random(7)
    rand = [m["member_id"] for m in roster]
    rng.shuffle(rand)

    def at(order):
        return [{"k": k, "precision": len(set(order[:k]) & pos) / k, "recall": len(set(order[:k]) & pos) / len(pos)} for k in ks]

    return {"n": len(roster), "positives": len(pos), "ks": list(ks), "methods": [
        {"name": "Coverage Keeper risk points", "at": at(ranked)},
        {"name": "Baseline: soonest deadline first", "at": at(by_deadline)},
        {"name": "Baseline: random order", "at": at(rand)},
    ], "note": "Labels come from a synthetic latent model (with noise and unobserved factors) using the same feature families; the "
               "hand-set points were not fit to these labels. The roster's city and language mix and its base rates are calibrated to "
               "public CMS (MassHealth renewal outcomes) and ACS data, but the member-level dynamics are assumed. This tests ranking "
               "under assumed dynamics, not real-world accuracy."}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true", help="also run the LLM engines (needs API key or a filled cache)")
    ap.add_argument("--split", default="test", choices=["test", "dev", "all"])
    args = ap.parse_args()
    cases = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((ROOT / "data" / "cases").glob("*.json"))]
    rulebook.use(None)

    results = {"generated": time.strftime("%Y-%m-%d %H:%M"), "as_of": config.AS_OF.isoformat(), "pack": rulebook.active()["id"],
               "split": args.split, "n_cases": len(cases), "runs": []}
    print("deterministic engine ...")
    det_rows, det_runs, _ = run_engine(cases, "Deterministic", False, args.split)
    results["runs"] += det_runs
    primary_rows, primary_name = det_rows, "Deterministic"
    judge_cost = 0.0
    if args.llm:
        if config.MODE == "offline":
            print("PP_MODE=offline: skipping LLM run")
        else:
            print(f"LLM engine (mode={config.MODE}) ...")
            llm_rows, llm_runs, judge_cost = run_engine(cases, "LLM agents", True, args.split)
            results["runs"] += llm_runs
            primary_rows, primary_name = llm_rows, "LLM agents"
    off, on = results["runs"][-2], results["runs"][-1]
    results["ablation"] = {
        "engine": primary_name, "without_verifier": off["unsupported_rate"], "with_verifier": on["unsupported_rate"],
        "summary": (f"{primary_name}: unsupported claims {off['unsupported']}/{off['claims']} "
                    f"({100 * (off['unsupported_rate'] or 0):.1f}%) without the verifier vs {on['unsupported']}/{on['claims']} "
                    f"({100 * (on['unsupported_rate'] or 0):.1f}%) with it, judged by grounding checks"
                    f"{' + an independent ' + config.MODELS['judge'] + ' entailment judge' if primary_name != 'Deterministic' else ''}.")
                   + ("" if primary_name != "Deterministic" else " Deterministic drafts are template-built from grounded facts, so they are "
                                                                  "supported by construction; the ablation is meaningful for the LLM drafter (run with --llm)."),
        "judge_cost_usd": judge_cost,
    }
    results["fairness"] = fairness(primary_rows)
    results["risk"] = risk_eval()
    results["errors"] = [{"case_id": r["case_id"], "title": r["title"],
                          "detail": f"ranking={r['ranking']} want={r['want']} gaps={r['gaps']} want_gaps={r['want_gaps']}"}
                         for r in primary_rows if (args.split == "all" or r["split"] == args.split)
                         and not (r["top1"] and r["sufficiency"] and not r["fp"] and not r["fn"])]
    results["per_case"] = primary_rows
    results["note"] = (f"{len(cases)} synthetic cases ({sum(c['split'] == 'dev' for c in cases)} dev / {sum(c['split'] == 'test' for c in cases)} "
                       f"test); headline numbers on the '{args.split}' split. The deterministic engine was written alongside the synthetic "
                       "document templates (all splits), so its scores are an upper bound on template-like documents, not evidence of "
                       "generalisation. Small n: one case = ~4 points.")

    (ROOT / "eval" / "results.json").write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
    md = ["# Coverage Keeper evaluation results", "", f"Generated {results['generated']} · as-of date {results['as_of']} · pack `{results['pack']}`", "",
          results["note"], "", "| Run | Split | n | Top-1 | Top-2 | Sufficiency | Gap P | Gap R | Outcome (R/R/T) | Key date | Transition told eligible | Eligible told to move | Unsupported claims | Latency/case | Cost/case |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    pct = lambda x: "–" if x is None else f"{100 * x:.0f}%"
    for r in results["runs"]:
        md.append(f"| {r['name']} | {r['split']} | {r['n']} | {pct(r['top1'])} | {pct(r['top2'])} | {pct(r['sufficiency_acc'])} | "
                  f"{pct(r['gap_precision'])} | {pct(r['gap_recall'])} | {pct(r['outcome_acc'])} | {pct(r['key_date_acc'])} (n={r['key_date_n']}) | "
                  f"{pct(r['transition_told_eligible_rate'])} (n={r['transition_n']}) | "
                  f"{pct(r.get('eligible_told_to_move_rate'))} (n={r.get('eligible_n', 0)}) | {r['unsupported']}/{r['claims']} ({pct(r['unsupported_rate'])}) | "
                  f"{r['latency_ms_mean']} ms | ${r['cost_usd_mean']:.4f} |")
    md += ["", "**Verifier ablation:** " + results["ablation"]["summary"], "", "## Risk flagging", "",
           "| Method | " + " | ".join(f"P@{k} | R@{k}" for k in results["risk"]["ks"]) + " |", "|---|" + "---|---|" * len(results["risk"]["ks"])]
    for m in results["risk"]["methods"]:
        md.append(f"| {m['name']} | " + " | ".join(f"{pct(a['precision'])} | {pct(a['recall'])}" for a in m["at"]) + " |")
    md += ["", results["risk"]["note"], ""]
    for dim, rows in results["fairness"].items():
        md += [f"## Fairness by {dim.replace('_', ' ')} ({primary_name}, all cases)", "", "| Group | n | Top-1 | Gap recall | Gap precision |", "|---|---|---|---|---|"]
        md += [f"| {r['group']} | {r['n']} | {pct(r['top1'])} | {pct(r['gap_recall'])} | {pct(r['gap_precision'])} |" for r in rows]
        md.append("")
    if results["errors"]:
        md += ["## Errors", ""] + [f"- **{e['case_id']}** {e['title']}: {e['detail']}" for e in results["errors"]]
    (ROOT / "eval" / "RESULTS.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md[:12 + len(results["runs"])]))


if __name__ == "__main__":
    main()
