# Slide outline (6 slides)

**1. The problem: Maria**
- Maria, 34, Lawrence, Spanish-speaking, cares for her mother after a stroke. *(Illustrative composite.)*
- Likely exempt as a caregiver, but she doesn't know it. The MassHealth letter arrives in English; she has 30 days.
- Miss it → coverage ends → her diabetes prescriptions stop. The plan loses a member.

**2. Impact**
- 72–73% of Medicaid disenrollments in the 2023 unwinding were procedural (KFF).
- From Jan 1, 2027, Massachusetts **Medicaid** (MassHealth) adds work requirements + six-month renewals: ~175,000 expected to lose coverage.
- Every eligible member lost = lost capitation revenue + broken care. Reminders aren't enough: the hard part is the evidence.

**3. How it works**
- Pipeline: risk flag → outreach → intake → extraction → rules → gap → follow-up → drafting → verifier → translation → human confirms.
- Deterministic rules for thresholds and dates; Claude for interpretation, extraction, drafting, translation (Haiku / Sonnet / Opus by stage).
- **Policy packs**: swap the pack, not the code (MassHealth pack + an illustrative employer pack).

**4. Guardrails and responsible AI**
- Never decides eligibility; a human confirms before sending.
- Every claim is cited to a document quote + a regulation quote; the verifier removes unsupported claims.
- `needs_confirmation` on ambiguous rules; synthetic data only; clear statement of what leaves the machine.
- Fairness by language and case type; no dark patterns; risk flags only offer help, never deny.

**5. Evaluation**
- 46 synthetic cases with hard edge cases, held-out test split: pathway top-1 / top-2, gap precision / recall.
- Headline: unsupported-claim rate with vs without the verifier (LLM drafts, independent Opus judge).
- Risk flags: P@20 80% vs 55% (deadline-first) vs 30% (random) on the 200-member synthetic roster.
- Latency and cost per case; honest limitations (synthetic, small n, template-tuned baseline).

**6. Innovation + business model**
- Others remind; we **resolve the case**: pathway, missing evidence, packet, third-party request, tracking.
- Buyer: health plans (Medicaid MCOs first). Retained members = retained premium/capitation.
- Works across Medicaid, Medicare Advantage, marketplace, employer and non-US private insurance via packs.
- Close: "Insurers lose members to paperwork, not ineligibility. Our agents finish the paperwork."
