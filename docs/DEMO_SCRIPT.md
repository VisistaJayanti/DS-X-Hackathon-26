# 2-minute demo script

**Setup (before going on stage):** `PP_MODE=replay python server.py` with the cache filled by one `python eval/run_eval.py --llm` run, so nothing depends on the venue Wi-Fi. Open http://127.0.0.1:8000 on the **Plan view**. Zoom the browser to 110%.

Say up front: *"Everything you'll see is synthetic. Maria is an illustrative composite, not a real person."*

| Time | Screen | Say |
|---|---|---|
| 0:00 | Plan view | "In the 2023 Medicaid unwinding, about 72% of people who lost coverage lost it for paperwork, not ineligibility. In January, Massachusetts adds work requirements for Medicaid: about 175,000 people are expected to lose MassHealth. For a health plan, every eligible member lost is lost revenue. Outreach tools send reminders. Coverage Keeper finishes the paperwork." |
| 0:15 | Roster, Maria's highlighted row | "This is a plan's roster. Maria is flagged, and here's why, in plain points: her notice went out in English but she speaks Spanish, she moved, she missed a notice, we haven't reached her, and plan data hints at a caregiver exemption. Flags only decide who we help first, never who gets coverage." |
| 0:25 | Open Maria's case → **Run agents** | "Ten agents run in sequence; each one's input and output is inspectable." (Let the stages animate.) |
| 0:35 | Outreach card | "Outreach picks text and phone, in Spanish. Every message gives the agency's own phone line and an opt-out: no dark patterns." |
| 0:45 | Documents + Rules table | "Maria texts photos of her caregiver statement and her mother's neurology letter. The rules agent checks all 17 pathways against a rulebook where every rule is quoted from the federal regulation. It finds the likely pathway: caregiver of a person with a disability. But it needs evidence." |
| 1:00 | Gaps card + click D3 cite | "Here's the catch a reminder app can't make: the mother's letter names the stroke but never says she has a disability or needs daily care. Without that sentence, the exemption fails." |
| 1:10 | Request letter + packet | "So it drafts the request to the mother's doctor, quoting the federal definition and asking for exactly that statement, with a reply-by date five days before the deadline. The packet is on hold until it arrives, and a coordinator must confirm before anything is sent." |
| 1:20 | Member explanation (Spanish) | "And Maria gets a plain-language explanation in Spanish: what she may qualify for, what's missing, the deadline. It's day 12; she keeps her coverage, and the plan keeps a member." |
| 1:30 | Verifier log | "Every sentence is a claim tied to an exact quote and a cited rule. The verifier removes anything unsupported, and logs it." |
| 1:40 | Evaluation tab | "On held-out synthetic cases: pathway accuracy, missing-evidence precision and recall, and the headline: unsupported claims with versus without the verifier. Plus risk precision at the top 20 a coordinator can actually call, and results by language and case type." |
| 1:50 | Policy packs tab → switch to the illustrative employer pack → rerun | "Nothing in the agents is MassHealth-specific. Swap the policy pack (here, an illustrative employer dependent audit) and the same agents apply different rules. Medicaid, Medicare Advantage, marketplace, employer, even non-US insurers: a new pack, not new code." |
| 2:00 | | "Insurers lose members to paperwork, not ineligibility. Our agents finish the paperwork." |

**Backup:** if anything fails, switch the Engine to "deterministic only" and rerun. Every stage has a deterministic fallback.
