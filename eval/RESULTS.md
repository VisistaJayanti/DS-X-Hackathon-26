# Coverage Keeper evaluation results

Generated 2026-10-24 18:35 · as-of date 2026-10-24 · pack `masshealth_ce_2027`

54 synthetic cases (27 dev / 27 test); headline numbers on the 'test' split. The deterministic engine was written alongside the synthetic document templates (all splits), so its scores are an upper bound on template-like documents, not evidence of generalisation. Small n: one case = ~4 points.

| Run | Split | n | Top-1 | Top-2 | Sufficiency | Gap P | Gap R | Outcome (R/R/T) | Key date | Transition told eligible | Eligible told to move | Unsupported claims | Latency/case | Cost/case |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Deterministic - verifier OFF | test | 27 | 100% | 100% | 100% | 100% | 100% | 100% | 100% (n=4) | 0% (n=4) | 0% (n=23) | 0/429 (0%) | 1 ms | $0.0000 |
| Deterministic - verifier ON | test | 27 | 100% | 100% | 100% | 100% | 100% | 100% | 100% (n=4) | 0% (n=4) | 0% (n=23) | 0/429 (0%) | 1 ms | $0.0000 |

**Verifier ablation:** Deterministic: unsupported claims 0/429 (0.0%) without the verifier vs 0/429 (0.0%) with it, judged by grounding checks. Deterministic drafts are template-built from grounded facts, so they are supported by construction; the ablation is meaningful for the LLM drafter (run with --llm).

## Risk flagging

| Method | P@20 | R@20 | P@40 | R@40 | P@60 | R@60 |
|---|---|---|---|---|---|---|
| Coverage Keeper risk points | 80% | 31% | 62% | 49% | 58% | 69% |
| Baseline: soonest deadline first | 15% | 6% | 28% | 22% | 25% | 29% |
| Baseline: random order | 35% | 14% | 20% | 16% | 25% | 29% |

Labels come from a synthetic latent model (with noise and unobserved factors) using the same feature families; the hand-set points were not fit to these labels. The roster's city and language mix and its base rates are calibrated to public CMS (MassHealth renewal outcomes) and ACS data, but the member-level dynamics are assumed. This tests ranking under assumed dynamics, not real-world accuracy.

## Fairness by language (Deterministic, all cases)

| Group | n | Top-1 | Gap recall | Gap precision |
|---|---|---|---|---|
| en | 36 | 100% | 100% | 100% |
| es | 9 | 100% | 100% | 100% |
| ht | 2 | 100% | 100% | 100% |
| pt | 3 | 100% | 100% | 100% |
| vi | 3 | 100% | 100% | 100% |
| zh | 1 | 100% | 100% | 100% |

## Fairness by case type (Deterministic, all cases)

| Group | n | Top-1 | Gap recall | Gap precision |
|---|---|---|---|---|
| caregiving | 7 | 100% | 100% | 100% |
| education | 5 | 100% | 100% | 100% |
| medical frailty | 9 | 100% | 100% | 100% |
| no pathway | 6 | 100% | 100% | 100% |
| other exemption | 5 | 100% | 100% | 100% |
| out of scope | 2 | 100% | 100% | 100% |
| pregnancy/postpartum | 5 | 100% | 100% | 100% |
| work/income | 15 | 100% | 100% | 100% |

## Fairness by want outcome (Deterministic, all cases)

| Group | n | Top-1 | Gap recall | Gap precision |
|---|---|---|---|---|
| recover | 2 | 100% | 100% | 100% |
| recover_expired | 1 | 100% | 100% | 100% |
| retain | 43 | 100% | 100% | 100% |
| transition | 8 | 100% | 100% | 100% |

