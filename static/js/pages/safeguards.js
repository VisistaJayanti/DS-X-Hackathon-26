// Safeguards: the responsible-AI commitments, written for coordinators and reviewers.
export const title = () => "Safeguards";

const ITEMS = [
  ["It never decides eligibility", "It says which pathway the documents point to. The verifier removes wording such as \"is eligible\" or \"approved\", and packets stay drafts until a coordinator approves them."],
  ["Every sentence is traceable", "Each drafted sentence carries an exact document quote or a rule from the pack, with its source text. The verifier removes anything it can't trace and logs what it removed."],
  ["Unclear rules are marked, not guessed", "Rules whose wording isn't confirmed against an official source show \"to confirm\" wherever they're used, such as medical-frailty letters and postpartum length."],
  ["What leaves the machine", "Only synthetic data. In live mode, document text goes only to the configured model provider's API. Free tiers may keep prompts, which is acceptable only because the data is synthetic. Saved responses stay in a local folder that git ignores."],
  ["Results are reported by group", "The evaluation script (eval/run_eval.py, results in eval/RESULTS.md) breaks results down by member language, type of case and outcome, so weaker performance for any group is visible."],
  ["No pressure in outreach", "Every message gives the agency's own phone line and a way to stop texts, never asks for a Social Security number by text, and never implies a decision."],
  ["Recovery without promises", "Members dropped for paperwork are told they may get coverage back by a dated deadline, and that the agency decides. Nothing says coverage will be reinstated."],
  ["Neutral options when coverage may end", "When the evidence suggests someone may no longer qualify, options are listed in no order of preference and the member chooses. A navigator confirms before anything changes."],
  ["Risk flags only bring help sooner", "The risk score is a visible list of reasons and points. It orders who gets help first and is never used to deny, delay or deprioritise anyone."],
  ["People stay in the loop", "Coordinators and navigators review every packet, letter and message. Machine translations are labelled and need a native speaker's review before real use."],
];

export async function render(el) {
  el.innerHTML = `
  <header class="page-head"><h1>Safeguards</h1></header>
  <p class="lede">Coverage Keeper does paperwork for people who could lose health coverage, so every output is built to be checked, traced and corrected by a person.</p>
  <dl class="safeguards">${ITEMS.map(([h, p]) => `<div><dt>${h}</dt><dd>${p}</dd></div>`).join("")}</dl>`;
}
