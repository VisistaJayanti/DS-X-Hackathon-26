# CLAUDE.md: guide for agents working on Coverage Keeper

Coverage Keeper is an insurer-agnostic AI member-retention layer. It flags health-plan members at risk of losing coverage over paperwork, reaches them in their language, finds the compliance/exemption pathway their documents support, catches missing evidence, drafts a cited packet and third-party request letters, and verifies every claim. Demo program: the MassHealth (Massachusetts **Medicaid**, not Medicare) community-engagement requirement starting Jan 1, 2027. Hackathon project (Hackachusetts 2026, BU DS+X). Read `README.md` for the product story and `eval/RESULTS.md` for current numbers.

## Hard rules

- **Never push, publish, or create remote repos/PRs.** The owner pushes to GitHub themselves. Don't run `git push`, and don't commit unless the owner asks.
- **Synthetic data only.** Never add real member data, real names of private people, or real documents. The demo member "Maria" is an illustrative composite and must stay labelled as such.
- **No secrets in the repo.** API keys (`GROQ_API_KEY`, `GEMINI_API_KEY`, `CEREBRAS_API_KEY`, `OPENROUTER_API_KEY`, `PP_CUSTOM_API_KEY`, `ANTHROPIC_API_KEY`) come from the environment or the git-ignored `.env`, which `keeper/config.py` loads. The committed template `.env.example` must only ever hold blank placeholders. `.env`, `cache/`, `data/custom/` and `sources_raw/` are git-ignored; keep them that way.
- **Never let the tool decide eligibility.** Output language is "likely pathway" or "documents support". The verifier (`keeper/stages/verify.py`, `DECISION` regex) strips "is eligible / is exempt / approved / guaranteed". Don't weaken it.
- **Don't invent rules.** Every rule in a pack carries a source URL and a verbatim quote. If you can't fetch and quote a source, mark the rule `needs_confirmation: true` (or `illustrative` for demo packs) instead of filling gaps from memory. After editing a rulebook, run `python scripts/check_rulebook_quotes.py`.
- **Keep the demo working offline.** Every LLM stage must keep a deterministic fallback, and replay mode (cached responses) must keep working. Don't add hard network dependencies.
- **Don't build income verification integrations.** That's deliberately left to CMS's Emmy and vendors.
- Outreach must always give the agency's direct contact line, offer text opt-out, never ask for an SSN by text, and never use pressure or dark patterns. Risk flags may only prioritise *help*, never deny or deprioritise anyone.

## Commands

```bash
pip install -r requirements.txt            # Python 3.9+ (dev machine is 3.9: no `X | Y` types, no match statements)
python data/generate_cases.py              # regenerate 46 labelled synthetic cases -> data/cases/
python data/generate_roster.py             # regenerate 200-member synthetic roster -> data/roster.json
python data/fetch_calibration.py           # re-download CMS + ACS aggregates -> data/calibration/ma_calibration.json (network)
python server.py                           # UI at http://127.0.0.1:8000  (#autorun=C46 runs Maria's case on load)
python scripts/smoke.py [CASE_ID]          # fast offline check of stages 1-4 vs labels (expects 46/46)
python eval/run_eval.py                    # deterministic eval -> eval/results.json + eval/RESULTS.md
python eval/run_eval.py --llm              # LLM agents + independent judge (needs API key; responses cached)
python scripts/check_rulebook_quotes.py    # verify verbatim quotes against sources_raw/ downloads
```

Environment variables:
- `PP_MODE` = `live` | `replay` | `offline`. Default: `live` if a key is set for any configured provider, else `replay`.
- `PP_AS_OF`: fixed "today", default `2026-10-24`, keeps deadlines reproducible.
- `PP_PACK`: default pack.
- `PP_MODELS` = `free` | `anthropic`: model preset. Default: `anthropic` if `ANTHROPIC_API_KEY` is set, else `free`.
- `PP_MODEL_<STAGE>` = `provider:model`: per-stage override. Stages are `INTAKE`, `EXTRACT`, `INTERPRET`, `DRAFT`, `TRANSLATE`, `VERIFY`, `JUDGE` and `OCR`.
- `PP_RPM_<PROVIDER>`, `PP_MAX_TOKENS_<PROVIDER>`: free-tier pacing and completion cap.
- `PP_CUSTOM_BASE_URL`: base URL for the `custom` OpenAI-compatible provider.

On Windows use `PYTHONIOENCODING=utf-8` when printing non-English output to the console.

## Architecture

```
server.py                  FastAPI; /api/run/{case} streams stage events over SSE
static/                    vanilla JS UI, no build step (index.html, app.js, style.css)
keeper/
  pipeline.py              orchestrator: risk -> outreach -> intake -> extract -> rules -> gaps
                           -> followup -> draft -> verify -> translate; records a per-stage trace
  rulebook.py              ACTIVE POLICY PACK accessor (thread-local; pipeline sets it from case["pack"])
  risk.py / plan.py        transparent points risk score; plan-view aggregation
  llm.py                   Anthropic + OpenAI-compatible clients (Groq, Gemini, Cerebras, OpenRouter, custom),
                           JSON-schema outputs checked locally (_conform), disk cache, pacing, cost metering
  docs.py textutil.py      quote grounding, line numbers, date/money parsing, language guess
  i18n.py                  generic member-explanation templates (6 languages)
  stages/                  one module per agent; each run() returns (output, engine, note)
packs/<pack_id>/           pack.json (program, pathways->evaluator+params, gap codes, doc types,
                           keywords, languages) + rules.json (cited rules with verbatim quotes)
data/                      generators for cases and roster (outputs are committed for reproducibility)
eval/run_eval.py           one-command evaluation
docs/                      demo script, Devpost text, slide outline
```

Key design points:
- **Program-agnostic core.** All program specifics live in the pack. Rules are generic evaluators in `keeper/stages/rules.py` (`EVALUATORS` dict: `threshold`, `enrollment`, `combination`, `dependent_child`, `caregiver_disabled`, `clinician_interpretation`, `fact_present`, ...) parameterised by the pack. To support a new program, add a pack. Add a new evaluator only when no existing one fits, and keep it free of program constants. Don't hard-code MassHealth/Medicaid/US specifics in agent code or prompts; prompts pull `program.domain_context` from the pack.
- **Deterministic where possible.** Thresholds, ages, dates and deadlines are code. The LLM does document classification, extraction, clinician-letter interpretation, drafting, translation and entailment checks.
- **Grounding contract.** Extracted facts must carry a quote that appears verbatim in the document (`extract._ground` drops the rest). Drafts are lists of typed claims (`fact` = doc_id + quote, `finding` / `rule` = rule_id, `request`, `boilerplate`). The verifier checks quote, rule, numbers, decision language and (live mode) LLM entailment. Keep this contract if you change drafting.
- **Two engines per LLM stage.** `use_llm=True` tries the configured model and falls back to deterministic on `LLMUnavailable`. That covers a missing key, a network error, a rate limit, or a response that fails the stage schema. The stage's `engine` field in the trace reports which ran; the UI shows it.
- **Models** (in `keeper/config.py`, as `provider:model`):
  - The `free` preset spreads stages over Groq, Gemini and Cerebras free tiers so no single daily quota runs out.
  - Keep the verifier and the eval judge on different model families from the drafter.
  - OpenAI-compatible calls try strict `json_schema` mode first. If a model rejects it with HTTP 400, `llm.py` remembers that and uses `json_object` mode with the schema in the prompt.
  - Free models don't all enforce schemas, so every stage output goes through `llm._conform`, and stage code can rely on the schema shape.
  - The `anthropic` preset uses Haiku 5.5 for intake; Sonnet 5.5 for extraction, drafting, translation and the verifier; and Opus 5.5 for interpretation and the eval judge. Opus/Sonnet 5.5 reject forced `tool_choice` and disabled thinking, so we use `output_config.format` JSON schemas and don't send temperature.
- Changing a prompt or schema changes the cache key, so re-run `--llm` to refill the cache before a demo.

## Data and evaluation conventions

- Case JSON: `member` (incl. `notice_received_date`, `lookback_months`, `language`), `documents` (`doc_id`, `filename`, `text`), `labels` (`correct_pathways` = any acceptable top-1, `"NONE"` for no pathway; `evidence_sufficient`; `gaps` = gap codes from the pack). Splits alternate dev/test; report headline numbers on **test**.
- When you add a case, add labels and run `scripts/smoke.py`. When you add a gap code, add it to **every** pack's `gap_codes` with `ask`, `fix`, `member_text` (6 languages) and optional `requests`.
- Be honest in reported numbers. The deterministic engine was tuned on the same templates (an upper bound), risk labels come from a synthetic latent model, and n is small. Don't remove these caveats from README/RESULTS.
- Roster calibration: `generate_roster.py` reads `data/calibration/ma_calibration.json` (committed). That file holds only public, aggregate CMS/ACS numbers with sources, method and caveats. The city mix, language-by-city and the subject/base rates come from it, and the latent label intercept is solved to match the CMS procedural rate. Real aggregate data is fine for calibration; real member-level data is not. If you re-run `fetch_calibration.py`, regenerate the roster, re-run the eval, and update the README/SLIDES/DEVPOST risk numbers.

## Current state / open work (as of 2026-10-24)

- **The LLM paths have never been executed** (no API key was available while building). First task for anyone with a key: `python eval/run_eval.py --llm`, fix any schema/parsing errors, then update the "LLM agents" row and ablation sentence in `README.md` from `eval/RESULTS.md`.
- mass.gov blocked automated fetching (HTTP 403). MassHealth-specific wording ($580 phrasing, "part-time", 45-day renewal form, blue envelope, postpartum length) is marked `needs_confirmation`. Fetch and quote it properly if you can, then clear the flag.
- Nice to have: a paraphrased "stress" case set (to show where the deterministic engine breaks), a population/EJ prioritisation view (`h2`/healthcare kit data, area-level only), and native-speaker review of the translations in `keeper/i18n.py`, `keeper/stages/outreach.py` and the packs.
- The second pack (`employer_dependent_audit_demo`) is illustrative with made-up rules. Keep `illustrative: true` and the UI label unless it's replaced with real, cited rules.
