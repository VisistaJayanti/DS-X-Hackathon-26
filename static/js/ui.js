// Shared UI helpers: escaping, dates, plain-language labels, the deadline window bar, provenance notes.

export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

export const LANG = { en: "English", es: "Spanish", pt: "Portuguese", ht: "Haitian Creole", vi: "Vietnamese", zh: "Chinese" };

export const OUTCOME = {
  retain: { label: "Keep covered", tone: "retain" },
  recover: { label: "Recover coverage", tone: "recover" },
  recover_expired: { label: "Recovery window closed", tone: "closed" },
  transition: { label: "Move to new coverage", tone: "transition" },
};

export const PATH_STATUS = {
  met: { label: "Documents support it", tone: "ok" },
  insufficient: { label: "Missing evidence", tone: "warn" },
  not_met: { label: "Not supported", tone: "quiet" },
};

export const KIND = { compliance: "Meets the work or income rule", exemption: "Exemption", out_of_scope: "Rule doesn't apply" };

export const MEMBER_STATUS = {
  flagged: "Needs first contact", contacted: "Contacted", documents_received: "Documents received",
  packet_ready: "Packet ready to review", submitted: "Submitted to the agency",
};

export const ASK = { clinician: "the doctor", school: "the school", employer: "the employer", navigator: "a navigator", member: "the member" };

// Member names carry a "(synthetic)" or "(illustrative composite)" label; show it as a tag, not inside the name.
export function splitName(name) {
  const m = String(name || "").match(/^(.*?)\s*\(([^)]+)\)\s*$/);
  return m ? { name: m[1], tag: m[2] } : { name: name || "", tag: "" };
}
// In lists, the sidebar already says every member is synthetic; only "illustrative composite" stays visible there.
export const nameHTML = (full, { inList = false } = {}) => {
  const { name, tag } = splitName(full);
  const show = tag && !(inList && tag === "synthetic");
  return `${esc(name)}${show ? ` <span class="tag">${esc(tag)}</span>` : ""}`;
};
export const firstName = (full) => splitName(full).name.split(" ")[0];

// ---------------------------------------------------------------- dates
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export const parseDay = (iso) => (iso ? new Date(iso + "T12:00:00") : null);
export const dayDiff = (a, b) => Math.round((parseDay(b) - parseDay(a)) / 86400000);
export function fmtDate(iso, asOf) {
  if (!iso) return "";
  const d = parseDay(iso);
  const sameYear = asOf && parseDay(asOf).getFullYear() === d.getFullYear();
  return `${MONTHS[d.getMonth()]} ${d.getDate()}${sameYear ? "" : ", " + d.getFullYear()}`;
}
export function daysLeftText(n) {
  if (n == null) return "";
  if (n === 0) return "due today";
  if (n === 1) return "1 day left";
  if (n > 0) return `${n} days left`;
  return n === -1 ? "1 day overdue" : `${-n} days overdue`;
}
export const urgency = (n) => (n == null ? "none" : n < 0 ? "over" : n <= 7 ? "critical" : n <= 14 ? "soon" : "ok");
export const addDays = (iso, n) => { const d = parseDay(iso); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10); };

// ---------------------------------------------------------------- the window bar
// A ruler from the day a window opened to the day it closes, with today and any intermediate marks.
export function windowBar({ start, end, today, marks = [], tone = "retain", size = "lg", startLabel, endLabel }) {
  if (!start || !end) return "";
  const span = Math.max(1, dayDiff(start, end));
  const pos = (iso) => Math.max(0, Math.min(100, (100 * dayDiff(start, iso)) / span));
  const left = dayDiff(today, end);
  const t = pos(today);
  const state = urgency(left);
  const label = `${startLabel || "Opened"} ${fmtDate(start, today)}; ${endLabel || "closes"} ${fmtDate(end, today)}; ${daysLeftText(left)}`;
  if (size === "sm") {
    return `<span class="window window-sm tone-${tone} is-${state}" role="img" aria-label="${esc(label)}">
      <span class="window-track"><span class="window-elapsed" style="width:${t}%"></span></span></span>`;
  }
  return `<figure class="window window-lg tone-${tone} is-${state}" role="img" aria-label="${esc(label)}">
    <div class="window-track">
      <span class="window-elapsed" style="width:${t}%"></span>
      ${marks.map((m) => `<span class="window-tick" style="left:${pos(m.date)}%"></span>`).join("")}
      <span class="window-today" style="left:${t}%"><span>Today, ${fmtDate(today, today)}</span></span>
    </div>
    <figcaption class="window-scale">
      <span>${esc(startLabel || "Opened")}<b>${fmtDate(start, today)}</b></span>
      ${marks.map((m) => `<span class="window-mark" style="left:${pos(m.date)}%">${esc(m.label)}<b>${fmtDate(m.date, today)}</b></span>`).join("")}
      <span class="window-end">${esc(endLabel || "Closes")}<b>${fmtDate(end, today)}</b></span>
    </figcaption>
  </figure>`;
}

// ---------------------------------------------------------------- provenance
// Every section says how it was produced: computed by rules, or drafted by an AI model and checked.
export function provenance(kind, html) {
  return `<p class="prov prov-${kind}"><span class="prov-mark" aria-hidden="true"></span><span>${html}</span></p>`;
}
export const modelNames = (stage) => [...new Set((stage?.llm_calls || []).map((c) => c.model.split(":").pop().split("/").pop()))];

// ---------------------------------------------------------------- citations
export function findLine(text, quote) {
  const norm = (s) => String(s || "").toLowerCase().replace(/[“”"]/g, '"').replace(/\s+/g, " ").trim();
  const q = norm(quote);
  if (!q) return null;
  const lines = String(text || "").split("\n");
  const i = lines.findIndex((l) => norm(l).includes(q.slice(0, 50)) || q.includes(norm(l)) && norm(l).length > 12);
  return i >= 0 ? i + 1 : null;
}
export function ruleLink(rules, sources, rid) {
  const r = rules[rid];
  if (!r) return rid ? `<span class="cite cite-rule">${esc(rid)}</span>` : "";
  const src = sources[r.source] || {};
  const confirm = r.needs_confirmation ? ` <span class="flag" title="${esc(r.confirmation_note || "Wording not yet confirmed against an official source")}">to confirm</span>` : "";
  return `<a class="cite cite-rule" href="${esc(r.url || src.url || "#")}" target="_blank" rel="noopener" title="${esc(r.quote)}">${esc(r.cite)}</a>${confirm}`;
}
export function docLink(cid, doc, quote, label) {
  const line = findLine(doc?.text, quote);
  return `<a class="cite cite-doc" href="#/case/${cid}/documents?doc=${esc(doc?.doc_id || "")}${line ? "&line=" + line : ""}" title="${esc(quote || "")}">${esc(label || doc?.doc_id || "")}${line ? `, line ${line}` : ""}</a>`;
}

export function empty(title, body, action = "") {
  return `<div class="empty"><h2>${esc(title)}</h2><p>${body}</p>${action}</div>`;
}
