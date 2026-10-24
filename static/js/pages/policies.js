// Policy packs: everything program-specific lives in a swappable pack.
import { S, loadPack } from "../store.js";
import { KIND, esc, ruleLink } from "../ui.js";

export const title = () => "Policy packs";

export async function render(el) {
  const p = S.packData;
  const rules = p.rulebook.rules;
  const toConfirm = rules.filter((r) => r.needs_confirmation).length;
  el.innerHTML = `
  <header class="page-head"><h1>Policy packs</h1></header>
  <p class="lede">The agents know nothing about a program until a pack tells them. A pack holds the pathways and thresholds, deadlines, document types and the rulebook, with each rule quoted word for word from its source.</p>
  <form class="filters"><label>Pack used for new runs<select data-pack>${S.packs.map((x) => `<option value="${x.id}" ${x.id === S.pack ? "selected" : ""}>${esc(x.name)}${x.illustrative ? " (illustrative, made-up rules)" : ""}</option>`).join("")}</select></label></form>
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
  <section aria-labelledby="pw-h"><h2 id="pw-h">Pathways</h2>
    <p class="sub">Each pathway is a generic check with settings from the pack, so a new program needs a new pack, not new code.</p>
    <div class="table-wrap"><table class="table"><thead><tr><th>Pathway</th><th>Type</th><th>Check and settings</th><th>Rule</th></tr></thead><tbody>
    ${p.pathways.map((w) => `<tr><td>${esc(S.rules[w.rule_id]?.name || w.id)}<span class="sub">${esc(w.id)}</span></td><td>${esc(KIND[w.kind] || w.kind)}</td>
      <td><code>${esc(w.evaluator)}</code><span class="sub">${esc(Object.entries(w.params || {}).map(([k, v]) => `${k.replace(/_/g, " ")} ${typeof v === "object" ? JSON.stringify(v) : v}`).join(", "))}</span></td><td>${ruleLink(S.rules, S.sources, w.rule_id)}</td></tr>`).join("")}
    </tbody></table></div></section>
  <details class="rest"><summary>The rulebook: ${rules.length} rules with their source text</summary>
    <div class="table-wrap"><table class="table"><thead><tr><th>Rule</th><th>Source text, word for word</th><th>Source</th></tr></thead><tbody>
    ${rules.map((r) => `<tr><td>${esc(r.name)}<span class="sub">${esc(r.id)}</span>${r.needs_confirmation ? '<span class="flag">to confirm</span>' : ""}</td>
      <td class="quote">${esc(r.quote)}${r.confirmation_note ? `<span class="sub">${esc(r.confirmation_note)}</span>` : ""}</td>
      <td>${ruleLink({ [r.id]: { ...r, needs_confirmation: false } }, S.sources, r.id)}<span class="sub">${esc(r.source_status.replace(/_/g, " "))}</span></td></tr>`).join("")}
    </tbody></table></div></details>`;
  el.querySelector("[data-pack]").onchange = async (e) => { await loadPack(e.target.value); render(el); };
}
