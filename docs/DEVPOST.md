# Coverage Keeper: Devpost write-up

**Tagline:** Retain eligible members. Recover those dropped by mistake. Transition those who no longer qualify, so nobody falls into a gap.

## Inspiration
During the 2023 Medicaid unwinding, KFF found that about 72–73% of disenrollments were for procedural reasons in states that reported them: people lost coverage over paperwork, not eligibility. On January 1, 2027, Massachusetts Medicaid (MassHealth) adds federal work/community-engagement requirements and six-month renewals for expansion adults, and the state estimates about 175,000 people will lose coverage. Many are exempt (caregivers, people who are medically frail, people who are postpartum) but don't know it, send the wrong document, or miss the 30-day deadline. For a health plan, each of those members is lost revenue and broken care.

## What it does
Coverage Keeper is an AI member-retention layer for health plans, with care coordinators and navigators as the human in the loop.
- **Flags** members at risk of procedural loss, with transparent reasons (returned mail, language mismatch, missed notices, deadline).
- **Reaches them** on the right channel in their language: a text, a phone/voice-agent script, a notice-helper mailer, or a community-health-worker visit checklist.
- **Reads their documents**, extracts facts with exact quotes, and checks *every* pathway (80 hours, $580 income, education, combinations, 13 exemptions) against a rulebook quoted from the federal regulation.
- **Catches the gap** (e.g. "the doctor's letter names the stroke but never says it's a disability") and says exactly how to fix it.
- **Drafts** the response packet, the request to the clinician/school/employer, and a plain-language explanation in English, Spanish, Portuguese, Haitian Creole, Vietnamese or Chinese.
- **Verifies** every claim against a document quote and a cited rule, removing and logging anything unsupported.
- **Tracks** each case from flagged → contacted → documents received → packet ready → submitted.

**Three outcomes for every member at risk:**
- **Retain:** keep eligible members covered: find the pathway, catch the gap, draft the packet before the deadline.
- **Recover:** members already dropped for paperwork can be reconsidered without a new application if the missing papers arrive within 90 days of termination (42 CFR 435.916(a)(3)(iii)); the tool counts down the window and drafts the submission, without promising reinstatement.
- **Transition:** when the evidence suggests someone may no longer qualify (income rose, turning 65, postpartum coverage ending, moved), it lists next-coverage options neutrally (e.g. the Massachusetts Health Connector, Medicare), computes the enrol-by date to avoid a gap from the cited enrolment rules, and hands off to a navigator.

It never decides eligibility. The agency does, and a coordinator confirms before anything is sent.

## How we built it
- Python + FastAPI backend and a no-build vanilla-JS UI that streams each agent's work over server-sent events.
- Ten stages: risk flag → outreach → intake → extraction → rules → gap → follow-up → drafting → verifier → translation. Claude Haiku 5.5, Sonnet 5.5 and Opus 5.5 are assigned per stage by cost and difficulty, with JSON-schema structured outputs between stages.
- Deterministic code for thresholds, ages, dates and deadlines; the LLM for interpretation (does this letter say the condition impairs the ability to work?), messy extraction, drafting and translation. Every LLM stage has a deterministic fallback and an on-disk cache, so the demo runs offline.
- **Policy packs:** all program-specific content (rules with verbatim regulatory quotes, thresholds, exemptions, document types, gap fixes, notice conventions, languages) lives in a swappable pack. We ship a MassHealth pack and an explicitly illustrative employer-plan pack to show reuse.
- A synthetic evaluation set (46 labelled cases with hard edge cases, dev/test split) and a 200-member synthetic roster, with a one-command evaluation script. The roster's members are synthetic, but its shape is calibrated to real public data. City mix and preferred language by city come from ACS 2020–2024 (Medicaid-covered adults, and limited-English residents by language). The share of members who must respond (67%) and the paperwork-loss base rate (45% of those) come from CMS's MassHealth renewal outcomes during the unwinding.

## Challenges
- mass.gov blocked automated retrieval (HTTP 403), so we encoded rules from the federal interim final rule's full text and wrote a checker that confirms every quote appears verbatim. Anything we couldn't verify is labelled `needs_confirmation` in the UI.
- The rules genuinely are ambiguous: "part-time" vs "half-time", how long postpartum lasts, what a frailty letter must say. We chose to surface ambiguity rather than guess.
- Making LLM output auditable: we made every sentence a typed claim carrying its own evidence, so a verifier can check it mechanically.

## Accomplishments
- An end-to-end case, from risk flag to Spanish outreach to a caught evidence gap to a cited packet and doctor request, that runs live or fully offline.
- A verifier ablation (unsupported claims with vs without the verifier) judged by grounding checks plus an independent judge from a different model family.
- Risk flagging that beats "soonest deadline first" at the top-k a coordinator can actually contact (P@20 80% vs 15% on the CMS/ACS-calibrated synthetic roster).
- Program-agnostic agents: switching packs changes the rules, deadline and language without code changes.

## What we learned
Pathways interact in ways members and navigators easily miss: a tipped worker can log 82 hours and meet the hours test while
falling short of $580 on paper; a SNAP notice that says "exempt from SNAP work rules" is *not* the SNAP exemption, but the
reason it gives (caring for a child) may be another one. Checking every pathway, every time, is what an agent is good at.

## What's next
- Pilot with a Medicaid managed-care plan's care-coordination team; native-speaker review of all translations.
- Packs for Medicare Advantage, ACA marketplace re-enrollment, employer plans, and non-US private insurers.
- Integrations: plan CRM/case-management, secure document upload and SMS, the agency portals; consent-based income verification via CMS's Emmy and vendors (we deliberately don't rebuild that).
- Real-world evaluation with de-identified historical cases under a data-use agreement.

## Business model
Health plans pay per member per year, or per retained member. A retained member is retained premium/capitation revenue and continuity of care. One product works across lines of business and countries, because every program is a pack.
