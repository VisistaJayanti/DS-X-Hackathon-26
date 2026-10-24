// Members: the full roster, split into the three situations, with search, filters and paging.
import { S, getPlan } from "../store.js";
import { LANG, MEMBER_STATUS, daysLeftText, dayDiff, esc, fmtDate, nameHTML, splitName, urgency } from "../ui.js";

export const title = () => "Members";
const PAGE = 25;

const cleanReason = (t) => t.replace(/\s*\(points per notice\)/, "").replace(/ - they may/, ": they may");
const link = (params, patch) => {
  const p = new URLSearchParams(params);
  Object.entries(patch).forEach(([k, v]) => (v === "" || v == null ? p.delete(k) : p.set(k, v)));
  if (!("page" in patch)) p.delete("page");
  return `#/members?${p}`;
};

export async function render(el, _args, params) {
  const p = await getPlan();
  const asOf = S.status.as_of;
  const view = params.get("view") || "risk";
  const q = (params.get("q") || "").toLowerCase();
  const lang = params.get("lang") || "";
  const all = params.get("all") === "1";
  const page = Math.max(1, +params.get("page") || 1);

  const views = {
    risk: { label: "At risk", rows: p.rows.filter((r) => all || r.flagged) },
    recover: { label: "Dropped for paperwork", rows: p.recover },
    transition: { label: "Likely to lose eligibility", rows: p.transition },
  };
  let rows = views[view].rows.filter((r) => (!q || splitName(r.name).name.toLowerCase().includes(q) || r.member_id.toLowerCase().includes(q)) && (!lang || r.language === lang));
  const total = rows.length;
  rows = rows.slice((page - 1) * PAGE, page * PAGE);
  const pages = Math.max(1, Math.ceil(total / PAGE));

  const head = {
    risk: "<th>Member</th><th>Language</th><th>Why they were flagged</th><th>Notice due</th><th>Where things stand</th>",
    recover: "<th>Member</th><th>Coverage ended</th><th>Reason</th><th>Reconsideration window</th><th>Where things stand</th>",
    transition: "<th>Member</th><th>What changed</th><th>Coverage ends</th><th>Enroll by, to avoid a gap</th><th>Navigator hand-off</th>",
  }[view];
  const who = (r, extra = "") => `<td class="who">${r.case_id ? `<a href="#/case/${r.case_id}">${nameHTML(r.name, { inList: true })}</a>` : nameHTML(r.name, { inList: true })}
    <span class="sub">${esc(r.member_id)}${extra}${r.case_id ? `, case ${r.case_id}` : ""}</span></td>`;
  const when = (iso, n) => `<td class="when is-${urgency(n)}">${iso ? fmtDate(iso, asOf) : "None"}${n != null ? `<span class="sub">${daysLeftText(n)}</span>` : ""}</td>`;
  const body = rows.map((r) => {
    if (view === "risk") return `<tr>${who(r, `, ${esc(r.city)}, age ${r.age}`)}<td>${LANG[r.language] || r.language}</td>
      <td><ul class="why">${r.reasons.map((x) => `<li>${esc(cleanReason(x.text))}</li>`).join("")}</ul><span class="sub">Risk score ${r.score}</span></td>
      ${when(r.due, r.days_left)}<td>${r.flagged ? esc(MEMBER_STATUS[r.status] || r.status) : '<span class="muted">Not flagged</span>'}</td></tr>`;
    if (view === "recover") return `<tr>${who(r, `, ${LANG[r.language] || r.language}`)}<td>${fmtDate(r.termination_date, asOf)}</td><td>${esc(r.reason || "")}</td>
      ${when(r.window_ends, r.days_left)}<td>${r.recoverable ? esc(MEMBER_STATUS[r.status] || r.status) : "Window closed: new application"}</td></tr>`;
    const end = r.avoid_gap_by || r.window_closes;
    return `<tr>${who(r, `, ${LANG[r.language] || r.language}`)}<td>${esc(r.trigger || "No pathway found")}</td><td>${r.coverage_end ? fmtDate(r.coverage_end, asOf) : "Not known"}</td>
      ${when(r.avoid_gap_by, end ? dayDiff(asOf, end) : null)}<td>${r.handoff_done ? "Done" : '<span class="pending">Waiting</span>'}</td></tr>`;
  }).join("");

  el.innerHTML = `
  <header class="page-head"><h1>Members</h1></header>
  <nav class="segmented" aria-label="Which members">
    ${Object.entries(views).map(([k, v]) => `<a href="${link(params, { view: k, q: "", lang: "" })}" ${k === view ? 'aria-current="page"' : ""}>${v.label}<span>${k === "risk" ? p.rows.filter((r) => r.flagged).length : v.rows.length}</span></a>`).join("")}
  </nav>
  <form class="filters" data-filters role="search">
    <label>Search by name<input name="q" type="search" value="${esc(params.get("q") || "")}" placeholder="e.g. Maria"></label>
    <label>Language<select name="lang"><option value="">All languages</option>${Object.entries(LANG).map(([k, v]) => `<option value="${k}" ${k === lang ? "selected" : ""}>${v}</option>`).join("")}</select></label>
    ${view === "risk" ? `<label class="check"><input type="checkbox" name="all" value="1" ${all ? "checked" : ""}> Include members not flagged</label>` : ""}
    <button class="btn btn-quiet" type="submit">Apply</button>
  </form>
  ${total ? `<div class="table-wrap"><table class="table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>` :
    `<div class="empty"><h2>No members match</h2><p><a href="${link(params, { q: "", lang: "" })}">Clear the search and filters</a></p></div>`}
  ${pages > 1 ? `<nav class="pager" aria-label="Pages"><span>${(page - 1) * PAGE + 1} to ${Math.min(page * PAGE, total)} of ${total}</span>
    ${page > 1 ? `<a class="btn btn-quiet" href="${link(params, { page: page - 1 })}">Previous</a>` : ""}
    ${page < pages ? `<a class="btn btn-quiet" href="${link(params, { page: page + 1 })}">Next</a>` : ""}</nav>` : ""}
  ${view === "risk" ? `<p class="fine">${esc(p.retention.note)}</p>` : ""}`;

  el.querySelector("[data-filters]").onsubmit = (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    location.hash = link(params, { q: f.get("q").trim(), lang: f.get("lang"), all: f.get("all") || "" });
  };
  el.querySelectorAll("[data-filters] select, [data-filters] input[type=checkbox]").forEach((x) => (x.onchange = () => x.form.requestSubmit()));
}
