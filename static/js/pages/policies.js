// Policy packs: everything program-specific lives in a swappable pack. Pick one to use it for case pages and runs,
// and see what it would change for every member in the dataset compared with the default policy.
import { S, getImpact, setPack } from "../store.js";
import { KIND, OUTCOME, PATH_STATUS, esc, nameHTML, provenance, ruleLink } from "../ui.js";

export const title = () => "Policy packs";

const CHANGE = {
  loses: "Lose their pathway", outcome: "Different outcome", weaker: "Need more evidence",
  gains: "Gain a pathway", stronger: "Evidence now complete", same: "Same result",
};
const ORDER = ["loses", "outcome", "weaker", "gains", "stronger", "same"];

function result(r) {
  if (!r.pathway) return `<b>No pathway</b><span class="sub">${esc(OUTCOME[r.outcome]?.label || r.outcome)}</span>`;
  const st = PATH_STATUS[r.status];
  return `${esc(r.pathway)} <span class="pill pill-${st.tone}">${st.label}</span><span class="sub">${esc(OUTCOME[r.outcome]?.label || r.outcome)}</span>`;
}

function what(row) {
  const a = row.base, b = row.new;
  switch (row.change) {
    case "loses": return `Loses "${esc(a.pathway)}"${b.outcome === "transition" ? "; routed to new coverage" : ""}`;
    case "gains": return `Gains "${esc(b.pathway)}"`;
    case "outcome": return `${OUTCOME[a.outcome].label} becomes ${OUTCOME[b.outcome].label.toLowerCase()}`;
    case "weaker": return "Needs more evidence than before";
    case "stronger": return "Evidence now complete";
    default: return a.pathway === b.pathway ? "No change" : "Same result; this policy names the pathway differently";
  }
}

async function impactSection(params) {
  const base = S.status.default_pack;
  if (S.pack === base) {
    return `<section aria-labelledby="impact-h"><h2 id="impact-h">See what another policy would change</h2>
      <p>Pick another pack above to compare it with this one for every member in the dataset.</p></section>`;
  }
  const imp = await getImpact(S.pack, base);
  const baseName = S.packs.find((x) => x.id === base)?.name || base;
  const show = params.get("show") || "changed";
  const rows = imp.rows.filter((r) => (show === "changed" ? r.change !== "same" : show === "all" || r.change === show));
  const nChanged = imp.n - (imp.counts.same || 0);
  const tBase = imp.outcomes.base.transition || 0, tNew = imp.outcomes.new.transition || 0;
  const chip = (key, label, n) => `<a href="#/policies?show=${key}" ${show === key ? 'aria-current="page"' : ""}>${label}<span>${n}</span></a>`;
  return `<section aria-labelledby="impact-h" class="impact">
    <h2 id="impact-h">What would change for the ${imp.n} members in the dataset</h2>
    <p class="lede">If these members were under ${esc(S.packData.name)} instead of ${esc(baseName)}, ${imp.counts.loses || "none"} would lose the
      pathway their documents support, and ${tNew} would be routed to new coverage instead of ${tBase}.</p>
    ${provenance("rules", `Worked out by the rules engine, without AI, for all ${imp.n} synthetic cases under both policies. Open a member to see
      their full summary under this policy; run the agents there for AI-drafted letters.`)}
    <nav class="segmented" aria-label="Which members">
      ${chip("changed", "Changed", nChanged)}${ORDER.filter((k) => imp.counts[k]).map((k) => chip(k, CHANGE[k], imp.counts[k])).join("")}${chip("all", "All", imp.n)}
    </nav>
    <div class="table-wrap"><table class="table"><thead><tr><th>Member</th><th>Under ${esc(baseName)}</th><th>Under ${esc(S.packData.name)}</th><th>What changes</th></tr></thead>
    <tbody>${rows.map((r) => `<tr><td class="who"><a href="#/case/${r.case_id}">${nameHTML(r.name, { inList: true })}</a>
        <span class="sub">${esc(r.case_id)}: ${esc(r.title)}</span></td>
      <td>${result(r.base)}</td><td>${result(r.new)}</td><td>${what(r)}</td></tr>`).join("")}</tbody></table></div>
  </section>`;
}

export async function render(el, _args, params) {
  const p = S.packData;
  const rules = p.rulebook.rules;
  const toConfirm = rules.filter((r) => r.needs_confirmation).length;
  const impact = await impactSection(params);
  el.innerHTML = `
  <header class="page-head"><h1>Policy packs</h1></header>
  <p class="lede">The agents know nothing about a program until a pack tells them. A pack holds the pathways and thresholds, deadlines, document types and the rulebook, with each rule quoted word for word from its source.</p>
  <form class="filters"><label>Policy for case pages and new runs<select data-pack>${S.packs.map((x) =>
    `<option value="${x.id}" ${x.id === S.pack ? "selected" : ""}>${esc(x.name)}${x.illustrative ? " (illustrative, made-up rules)" : ""}</option>`).join("")}</select></label></form>
  <section aria-labelledby="pack-h">
    <h2 id="pack-h">${esc(p.name)}</h2>
    ${p.illustrative ? `<p class="alert">This pack is illustrative. Its rules are made up to show the same agents running on a different program.</p>` : ""}
    <p>${esc(p.summary)}</p>
    <dl class="stats stats-row">
      <div><dt>Line of business</dt><dd>${esc(p.line_of_business)}</dd></div>
      <div><dt>Where</dt><dd>${esc(p.jurisdiction)}</dd></div>
      <div><dt>Days to respond</dt><dd>${p.program.response_window_days}</dd></div>
      <div><dt>Rules</dt><dd>${rules.length}, ${toConfirm} to confirm</dd></div>
    </dl>
  </section>
  ${impact}
  <section aria-labelledby="pw-h"><h2 id="pw-h">Pathways</h2>
    <p class="sub">Each pathway is a generic check with settings from the pack, so a new program needs a new pack, not new code.</p>
    <div class="table-wrap"><table class="table"><thead><tr><th>Pathway</th><th>Type</th><th>Check and settings</th><th>Rule</th></tr></thead><tbody>
    ${p.pathways.map((w) => `<tr><td>${esc(S.rules[w.rule_id]?.name || w.id)}<span class="sub">${esc(w.id)}</span></td><td>${esc(KIND[w.kind] || w.kind)}</td>
      <td><code>${esc(w.evaluator)}</code><span class="sub">${esc(Object.entries(w.params || {}).map(([k, v]) => `${k.replace(/_/g, " ")} ${typeof v === "object" ? JSON.stringify(v) : v}`).join(", "))}</span></td><td>${ruleLink(S.rules, S.sources, w.rule_id)}</td></tr>`).join("")}
    </tbody></table></div></section>
  <details class="rest"><summary>The rulebook: ${rules.length} rules with their source text</summary>
    <div class="table-wrap"><table class="table"><thead><tr><th>Rule</th><th>Source text, word for word</th><th>Source</th></tr></thead><tbody>
    ${rules.map((r) => `<tr><td>${esc(r.name)}<span class="sub">${esc(r.id)}</span>${r.needs_confirmation ? '<span class="flag">to confirm</span>' : ""}</td>
      <td class="quote">${r.quote ? esc(r.quote) : "<i>No quote: not found in the downloaded sources</i>"}${r.confirmation_note ? `<span class="sub">${esc(r.confirmation_note)}</span>` : ""}</td>
      <td>${ruleLink({ [r.id]: { ...r, needs_confirmation: false } }, S.sources, r.id)}<span class="sub">${esc(r.source_status.replace(/_/g, " "))}</span></td></tr>`).join("")}
    </tbody></table></div></details>`;
  el.querySelector("[data-pack]").onchange = (e) => setPack(e.target.value);  // re-renders through onChange
}
