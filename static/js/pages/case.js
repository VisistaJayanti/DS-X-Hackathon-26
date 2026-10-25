// A case, split into pages by what produced the content:
//   summary   - the recommendation, worked out by rules        documents - the member's papers
//   letters   - drafted by an AI model or templates, verified   evidence  - every pathway and fact
//   agents    - how it was decided: each agent, engine, timing and the verifier log
import { S, clearRunError, getCase, outOf, rk, runCase, setPack, stageOf } from "../store.js";
import {
  ASK, KIND, LANG, OUTCOME, PATH_STATUS, daysLeftText, docLink, empty, esc, findLine, firstName, fmtDate, modelNames,
  nameHTML, provenance, ruleLink, splitName, windowBar,
} from "../ui.js";

const SUBS = { summary: "Summary", documents: "Documents", letters: "Letters", evidence: "Evidence", agents: "How it was decided" };
const STAGES = [
  ["risk", "Risk check"], ["outreach", "Outreach"], ["intake", "Sorting documents"], ["extract", "Reading documents"],
  ["rules", "Checking every pathway"], ["gaps", "Finding what's missing"], ["outcome", "Choosing the outcome"],
  ["followup", "Planning follow-up"], ["draft", "Drafting letters"], ["verify", "Checking every claim"], ["translate", "Translating"],
];
const ENGINE = {
  llm: "AI model", deterministic: "Rules", "llm+deterministic": "Rules, with AI reading the letters", "deterministic+llm": "Rules, with an AI check", "llm+rules": "AI model, gaps filled by rules",
  template: "Template", none: "Not needed", untranslated: "Not translated", english_fallback: "English fallback",
};

export const title = ([cid, sub]) => `${S.caseData[cid] ? splitName(S.caseData[cid].member.name).name : cid}: ${SUBS[sub || "summary"] || ""}`;

export async function render(el, [cid, sub = "summary"], params) {
  if (!SUBS[sub]) sub = "summary";
  const c = await getCase(cid);
  const t = S.runs[rk(cid)];
  const run = S.running[rk(cid)];
  const needsResult = sub !== "documents" && !(sub === "agents" && run);
  const body = !t && needsResult
    ? (run ? empty("The agents are working on this case", `Results appear here as soon as the run finishes. <a href="#/case/${cid}/agents">Watch each agent work</a>`) : notRun(c))
    : { summary, documents, letters, evidence, agents }[sub](c, t, cid, params, run);
  el.innerHTML = header(c, cid, t, run) + subnav(cid, sub) + progress(run) + `<div class="case-body">${body}</div>`;
  wire(el, cid, c, sub);
}

// ---------------------------------------------------------------- frame
function header(c, cid, t, run) {
  const m = c.member;
  const set = S.settings[cid] || {};
  const lang = set.lang || m.language || "en";
  const others = S.cases.map((x) => `<option value="${x.case_id}" ${x.case_id === cid ? "selected" : ""}>${x.case_id}: ${esc(x.title)}</option>`).join("");
  return `<header class="case-head">
    <div class="case-id">
      <label class="switcher"><span class="visually-hidden">Switch case</span><select data-switch>${others}</select></label>
      <h1>${nameHTML(m.name)}</h1>
      <dl class="facts">
        <div><dt>Age</dt><dd>${esc(m.age)}</dd></div>
        <div><dt>Prefers</dt><dd>${LANG[m.language] || esc(m.language)}</dd></div>
        ${m.household ? `<div><dt>Household</dt><dd>${esc(m.household)}</dd></div>` : ""}
        ${m.notice_received_date ? `<div><dt>Notice received</dt><dd>${fmtDate(m.notice_received_date, S.status.as_of)}</dd></div>` : ""}
      </dl>
    </div>
    <form class="run-box" data-run>
      <label class="policy-pick">Policy<select data-pack ${run && !run.error ? "disabled" : ""}>${S.packs.map((p) =>
        `<option value="${p.id}" ${p.id === S.pack ? "selected" : ""}>${esc(p.name)}${p.illustrative ? " (illustrative)" : ""}</option>`).join("")}</select></label>
      <button class="btn btn-primary" type="submit" ${run && !run.error ? "disabled" : ""}>${run && !run.error ? "Running…" : t ? "Run the agents again" : "Run the agents"}</button>
      <details class="run-settings"><summary>Run settings</summary>
        <label>Letter language<select name="lang">${Object.entries(S.status.languages).map(([k, v]) => `<option value="${k}" ${k === lang ? "selected" : ""}>${esc(v)}</option>`).join("")}</select></label>
        <label>Engine<select name="engine"><option value="auto" ${set.engine !== "offline" ? "selected" : ""}>AI models where available</option><option value="offline" ${set.engine === "offline" ? "selected" : ""}>Rules and templates only</option></select></label>
        <label class="check"><input type="checkbox" name="verifier" ${set.verifier === false ? "" : "checked"}> Check every claim (verifier)</label>
      </details>
      ${t ? `<p class="run-meta">Last run used ${t.summary.llm_calls} AI calls${t.summary.llm_calls ? "" : ", rules only"}</p>` : ""}
    </form>
  </header>`;
}

function subnav(cid, sub) {
  return `<nav class="subnav" aria-label="Case pages">${Object.entries(SUBS).map(([k, v]) =>
    `<a href="#/case/${cid}${k === "summary" ? "" : "/" + k}" ${k === sub ? 'aria-current="page"' : ""}>${v}</a>`).join("")}</nav>`;
}

function progress(run) {
  if (!run) return "";
  if (run.error) return `<div class="alert" role="alert"><p><strong>The run stopped.</strong> ${esc(run.error)}</p></div>`;
  const done = Object.fromEntries(run.stages.map((s) => [s.key, s.state]));
  const now = STAGES.find(([k]) => done[k] === "running");
  return `<div class="progress" role="status" aria-live="polite">
    <p>${now ? `${esc(now[1])}…` : "Starting…"}</p>
    <ol>${STAGES.map(([k, label]) => `<li class="is-${done[k] || "waiting"}" title="${esc(label)}"><span class="visually-hidden">${esc(label)}: ${done[k] || "waiting"}</span></li>`).join("")}</ol>
  </div>`;
}

function notRun(c) {
  return empty("Nothing has been worked out for this case yet",
    `Run the agents to read ${c.documents.length} document${c.documents.length === 1 ? "" : "s"}, check every pathway and draft the letters.
     Saved AI responses make a repeat run take seconds; a fresh run on the live models takes a few minutes.`,
    `<button class="btn btn-primary" data-action="run">Run the agents</button>`);
}

function wire(el, cid, c, sub) {
  const form = el.querySelector("[data-run]");
  const start = () => {
    const f = new FormData(form);
    S.settings[cid] = { lang: f.get("lang"), engine: f.get("engine"), verifier: f.get("verifier") === "on" };
    clearRunError(cid);
    runCase(cid, S.settings[cid]);
  };
  form.onsubmit = (e) => { e.preventDefault(); start(); };
  el.querySelectorAll("[data-action=run]").forEach((b) => (b.onclick = start));
  el.querySelector("[data-switch]").onchange = (e) => { location.hash = `#/case/${e.target.value}${sub === "summary" ? "" : "/" + sub}`; };
  el.querySelector("[data-pack]").onchange = (e) => setPack(e.target.value);  // re-renders through onChange
  const consent = el.querySelector("[data-consent]");
  if (consent) {
    const btn = el.querySelector("[data-approve]");
    consent.onchange = () => (btn.disabled = !consent.checked);
    btn.onclick = () => { btn.textContent = "Approved. In this demo nothing is sent."; btn.disabled = true; consent.disabled = true; };
  }
  el.querySelector(".line.is-focus")?.scrollIntoView({ block: "nearest" });
}

// ---------------------------------------------------------------- shared pieces
const sortedPaths = (rules) => [...rules.pathways].sort((a, b) => (rules.ranking.indexOf(a.pathway) + 1 || 99) - (rules.ranking.indexOf(b.pathway) + 1 || 99));
const docById = (c, id) => c.documents.find((d) => d.doc_id === id);
const status = (s) => `<span class="pill pill-${PATH_STATUS[s].tone}">${PATH_STATUS[s].label}</span>`;
const docLabel = (t, doc) => {
  if (!doc) return "";
  const type = outOf(t, "intake")?.documents.find((d) => d.doc_id === doc.doc_id)?.doc_type;
  return (type && S.packData.doc_labels?.[type]) || doc.filename;
};
function claimHTML(cl, c, cid) {
  const doc = cl.doc_id && docById(c, cl.doc_id);
  const cites = [doc ? docLink(cid, doc, cl.quote, cl.doc_id) : "", cl.rule_id ? ruleLink(S.rules, S.sources, cl.rule_id) : ""].filter(Boolean).join(" ");
  return `<p class="claim" data-kind="${esc(cl.kind)}">${esc(cl.text)}${cites ? ` <span class="cites">${cites}</span>` : ""}</p>`;
}
const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : "");
// A request letter only when a gap needs a third party to provide something (runs saved before the drafter
// enforced this can hold an empty or unneeded AI-drafted one).
function neededRequest(t) {
  const r = t.final.request;
  const gaps = outOf(t, "gaps")?.gaps || [];
  return r?.claims?.length && gaps.some((g) => S.packData.gap_codes?.[g.code]?.requests?.length) ? r : null;
}
// The outcome stage words the trigger in the member's language for their letter; coordinator pages use English.
const triggerLabel = (tr) => S.packData.transitions?.triggers?.[tr.trigger]?.label?.en || tr.trigger_label;
// Gap details are written for the trace ("D2 is in 'es'."); name the document and language instead.
function gapTitle(g, c, t) {
  const m = g.code === "DOC_TRANSLATION" && g.detail.match(/^(\w+) is in '(\w+)'/);
  if (!m) return g.detail;
  return `The ${docLabel(t, docById(c, m[1])).toLowerCase() || m[1]} is in ${LANG[m[2]] || m[2]}`;
}

// ---------------------------------------------------------------- summary
function summary(c, t, cid) {
  const asOf = S.status.as_of, prog = S.packData.program;
  const rules = outOf(t, "rules"), gaps = outOf(t, "gaps"), oc = outOf(t, "outcome") || { outcome: "retain" };
  const facts = outOf(t, "extract").facts;
  const paths = sortedPaths(rules);
  const best = paths.find((p) => p.pathway === t.summary.best_pathway);
  const first = firstName(c.member.name);
  const O = OUTCOME[oc.outcome] || OUTCOME.retain;
  const dl = gaps.deadline;
  const req = neededRequest(t);
  const pk = t.final.packet;
  let head, lines = [], bar = "", steps = [];

  if (oc.outcome === "retain") {
    head = best ? best.name : "No pathway is supported yet";
    lines.push(!best ? `None of the ${paths.length} pathways is supported by ${esc(first)}'s documents yet.`
      : t.summary.evidence_sufficient ? `${esc(first)}'s documents support this. The packet looks complete.`
      : `${esc(first)} likely qualifies this way, but the evidence is incomplete.`);
    if (dl) {
      lines.push(`Respond to ${esc(prog.agency)} by ${fmtDate(dl.due, asOf)}, ${daysLeftText(dl.days_left)}.`);
      bar = windowBar({ start: dl.notice_received, end: dl.due, today: asOf, tone: "retain", startLabel: "Notice received", endLabel: "Respond by",
        marks: req ? [{ date: dl.ask_third_party_by, label: "Ask for letters by" }] : [] });
    }
    if (req) steps.push(`Send the request letter to ${ASK[req.to] || esc(req.to)} and ask for a reply by ${fmtDate(dl?.ask_third_party_by, asOf)}. <a href="#/case/${cid}/letters#request">Open the request letter</a>`);
    if (best && !t.summary.evidence_sufficient) steps.push("When the missing evidence arrives, add it to the case and run the agents again.");
    if (!best) steps.push(`Go through the exemptions with ${esc(first)}. A document may be missing that would support one.`);
    if (pk.status !== "none") steps.push(`Review the response packet with ${esc(first)} and approve it. <a href="#/case/${cid}/letters#packet">Open the packet</a>`);
    if (dl) steps.push(`Send it to ${esc(prog.agency)} by ${fmtDate(dl.due, asOf)}.`);
  } else if (oc.outcome === "recover" || oc.outcome === "recover_expired") {
    const rc = oc.reconsideration;
    const open = oc.outcome === "recover";
    head = open ? "Coverage can likely be recovered" : "The recovery window has closed";
    lines.push(`Coverage ended on ${fmtDate(rc.termination_date, asOf)} for missing paperwork.`);
    lines.push(open ? `Send the missing papers by ${fmtDate(rc.ends, asOf)}, ${daysLeftText(rc.days_left)}, and a new application may not be needed.`
      : `The ${rc.window_days}-day window closed on ${fmtDate(rc.ends, asOf)}. ${esc(first)} needs to apply again.`);
    bar = windowBar({ start: rc.termination_date, end: rc.ends, today: asOf, tone: open ? "recover" : "closed", startLabel: "Coverage ended", endLabel: "Window closes",
      marks: open && req ? [{ date: rc.ask_third_party_by, label: "Ask for letters by" }] : [] });
    if (open) {
      if (req) steps.push(`Send the request letter to ${ASK[req.to] || esc(req.to)}. <a href="#/case/${cid}/letters#request">Open the request letter</a>`);
      steps.push(`Review the reconsideration submission with ${esc(first)} and approve it. <a href="#/case/${cid}/letters#packet">Open the submission</a>`);
      steps.push(`Send it to ${esc(prog.agency)} by ${fmtDate(rc.ends, asOf)}.`);
    } else {
      steps.push(`Help ${esc(first)} start a new application. The documents already collected can go with it.`);
    }
  } else {
    const tr = oc.transition, w = tr.window || {};
    head = cap(triggerLabel(tr));
    lines.push(`${esc(first)} may no longer qualify. The agency decides, and a navigator confirms before anything changes.`);
    if (w.avoid_gap_by) lines.push(`To avoid a gap in coverage, enroll by ${fmtDate(w.avoid_gap_by, asOf)}. The enrollment window closes ${fmtDate(w.closes, asOf)}.`);
    bar = windowBar({ start: w.opens, end: w.closes, today: asOf, tone: "transition", startLabel: "Window opens", endLabel: "Window closes",
      marks: w.avoid_gap_by ? [{ date: w.avoid_gap_by, label: "Enroll by, no gap" }] : [] });
  }
  const tr = oc.transition;
  if (tr && (oc.outcome === "transition" || oc.outcome === "recover_expired")) {
    steps.push("Share the hand-off note below with a navigator.");
    steps.push(`Go through the options with ${esc(first)}. They choose; the options are listed in no order of preference.`);
    if (tr.window?.avoid_gap_by) steps.push(`Enroll by ${fmtDate(tr.window.avoid_gap_by, asOf)} so coverage continues without a gap.`);
  }

  const missing = oc.outcome === "transition" ? "" : `<section class="missing" aria-labelledby="miss-h"><h2 id="miss-h">What's missing</h2>
    ${gaps.gaps.length ? `<ul class="gaps">${gaps.gaps.map((g) => `<li><h3>${esc(gapTitle(g, c, t))}</h3><p>${esc(g.fix)}</p><p class="sub">Who can provide it: ${ASK[g.ask] || esc(g.ask)}</p></li>`).join("")}</ul>`
      : `<p>Nothing is missing for this pathway.</p>`}
    ${!best && gaps.resources?.length ? `<p class="sub">Where to refer: ${gaps.resources.map((r) => `<a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.name)}</a>`).join(", ")}</p>` : ""}</section>`;
  const used = [...new Set((best?.evidence || []).map((fid) => facts.find((f) => f.fact_id === fid)?.doc_id).filter(Boolean))];

  return `${provenance("rules", `Worked out under <a href="#/policies">${esc(S.packData.name)}</a> by rules, from ${facts.length} facts read out of ${c.documents.length} document${c.documents.length === 1 ? "" : "s"}. ${esc(prog.agency)} decides eligibility.`)}
  <section class="answer tone-${O.tone}">
    <p class="outcome-tag">${O.label}</p>
    <h2 class="answer-head">${esc(head)}</h2>
    ${lines.map((l) => `<p class="answer-line">${l}</p>`).join("")}
    ${bar}
  </section>
  <div class="summary-grid">
    ${missing}
    <section aria-labelledby="steps-h"><h2 id="steps-h">Next steps</h2><ol class="steps">${steps.map((s) => `<li>${s}</li>`).join("")}</ol>
      ${used.length ? `<p class="sub">Based on ${used.map((id) => `<a href="#/case/${cid}/documents?doc=${id}">${esc(docLabel(t, docById(c, id)))}</a>`).join(", ")}. <a href="#/case/${cid}/evidence">See every pathway checked</a></p>` : ""}
    </section>
  </div>
  ${tr && (oc.outcome === "transition" || oc.outcome === "recover_expired") ? transitionPlan(tr) : ""}`;
}

function transitionPlan(tr) {
  const w = tr.window || {};
  return `<section class="plan" aria-labelledby="plan-h"><h2 id="plan-h">Next coverage, without a gap</h2>
    <p>${esc(cap(triggerLabel(tr)))}.${tr.coverage_end ? ` Coverage is expected to end ${fmtDate(tr.coverage_end, S.status.as_of)}.` : ""}</p>
    <p class="sub">Rules behind this: ${[tr.trigger_rule_id, w.rule_id, w.advance_rule_id].filter(Boolean).map((r) => ruleLink(S.rules, S.sources, r)).join(" ")}</p>
    <div class="plan-grid">
      <div><h3>Options for the member to choose from</h3><ul class="options">${tr.options.map((o) => `<li><b>${esc(o.name)}</b><span>${esc(o.contact)}</span></li>`).join("")}</ul></div>
      <div><h3>Documents to have ready</h3><ul>${tr.documents.map((d) => `<li>${esc(d)}</li>`).join("")}</ul></div>
    </div>
    <h3>Hand-off note for a navigator</h3><div class="sheet sheet-note">${esc(tr.handoff_note)}</div>
    <p class="fine">${esc(tr.neutral_routing_note)}</p></section>`;
}

// ---------------------------------------------------------------- documents
function documents(c, t, cid, params) {
  const docs = c.documents;
  const active = docById(c, params.get("doc")) || docs[0];
  const line = +params.get("line") || null;
  const mode = active.image && !line && params.get("mode") !== "text" ? "original" : "text";
  const cited = new Map();
  for (const f of outOf(t, "extract")?.facts || []) {
    if (f.doc_id !== active.doc_id) continue;
    const n = findLine(active.text, f.quote) || f.line;  // locate by the quote itself, so a stale line number can't mislead
    cited.set(n, (cited.get(n) || []).concat(f.type.replace(/_/g, " ")));
  }
  const base = `#/case/${cid}/documents?doc=${active.doc_id}`;
  return `<div class="docs">
    <nav class="doc-list" aria-label="Documents">${docs.map((d) => `<a href="#/case/${cid}/documents?doc=${d.doc_id}" ${d.doc_id === active.doc_id ? 'aria-current="page"' : ""}>
      <b>${esc(t ? docLabel(t, d) : d.filename)}</b><span>${esc(d.filename)}</span></a>`).join("")}</nav>
    <section class="doc-view" aria-label="${esc(active.filename)}">
      <div class="doc-tools">
        ${active.image ? `<nav class="toggle" aria-label="View"><a href="${base}" ${mode === "original" ? 'aria-current="page"' : ""}>Original</a><a href="${base}&mode=text" ${mode === "text" ? 'aria-current="page"' : ""}>Text the agents read</a></nav>` : ""}
        ${active.pdf ? `<a href="${esc(active.pdf)}" target="_blank" rel="noopener">Open the PDF</a>` : ""}
      </div>
      ${mode === "original" ? `<img class="doc-img" src="${esc(active.image)}" alt="${esc(active.filename)}">`
        : `${t ? `<p class="fine">Highlighted lines are the exact quotes the agents took facts from.${line ? " The darker line is the one you followed a link to." : ""}</p>` : ""}
           <pre class="doc-text">${active.text.split("\n").map((l, i) => {
             const n = i + 1, hit = cited.get(n);
             return `<span class="line${hit ? " is-cited" : ""}${n === line ? " is-focus" : ""}" ${hit ? `title="${esc(hit.join(", "))}"` : ""}><span class="ln">${n}</span><span class="tx">${esc(l) || " "}</span></span>`;
           }).join("")}</pre>`}
    </section></div>`;
}

// ---------------------------------------------------------------- letters
function letters(c, t, cid) {
  const draft = stageOf(t, "draft"), ver = outOf(t, "verify"), tr = stageOf(t, "translate");
  const oc = outOf(t, "outcome")?.outcome || "retain";
  const fin = t.final, first = firstName(c.member.name), lang = fin.member.language;
  const checked = ver ? ` The verifier checked ${ver.stats.claims} sentences, removed ${ver.stats.removed} and flagged ${ver.stats.flagged} for a closer look (<a href="#/case/${cid}/agents#verifier">see which</a>).` : "";
  const prov = !ver ? provenance("warn", "The verifier was off for this run, so these drafts are unchecked. Turn it on in Run settings before using them.")
    : draft.engine === "llm" ? provenance("ai", `Drafted by an AI model (${esc(modelNames(draft).join(", "))}).${checked} Read every letter before approving it.`)
    : provenance("template", `Written from fixed, reviewed templates${oc !== "retain" ? ", which recover and new-coverage letters always use so they never promise an outcome" : ""}.${checked}`);
  const pk = fin.packet, req = neededRequest(t);
  const out = outOf(t, "outreach"), fu = outOf(t, "followup");
  const PK = { ready: "Ready for review", hold: "On hold until the missing evidence arrives", none: "No packet for this case" };
  return `${prov}
  <section class="letter-block" aria-labelledby="mem-h"><h2 id="mem-h">Explanation for ${esc(first)}, in ${esc(LANG[lang] || lang)}</h2>
    <p class="sub">${tr.engine === "llm" ? `Translated by an AI model (${esc(modelNames(tr).join(", "))}) after the English was checked.` : tr.engine === "template" ? "Built from reviewed sentence templates." : ""} A native speaker should review it before real use.</p>
    <div class="sheet" lang="${esc(lang)}">${fin.member.sentences.map((s) => `<p>${esc(s.text)}</p>`).join("")}</div>
    ${lang !== "en" ? `<details class="english"><summary>Show the checked English version</summary><div class="sheet sheet-quiet">${fin.member.sentences.map((s) => `<p>${esc(s.en)}</p>`).join("")}</div></details>` : ""}
  </section>
  ${req ? `<section class="letter-block" id="request" aria-labelledby="req-h"><h2 id="req-h">${esc(req.title)}, to ${ASK[req.to] || esc(req.to)}</h2>
    <div class="sheet">${req.claims.map((cl) => claimHTML(cl, c, cid)).join("")}</div></section>` : ""}
  <section class="letter-block" id="packet" aria-labelledby="pk-h"><h2 id="pk-h">${oc === "recover" ? "Reconsideration submission" : "Response packet"} to ${esc(S.packData.program.agency)}</h2>
    <p class="sub">${PK[pk.status] || esc(pk.status)}</p>
    ${pk.sections.length ? `<div class="sheet">${pk.sections.map((s) => `<h3>${esc(s.heading)}</h3>${s.claims.map((cl) => claimHTML(cl, c, cid)).join("")}`).join("")}
      ${pk.enclosures?.length ? `<p class="enclosures">Enclosures: ${pk.enclosures.map(esc).join("; ")}</p>` : ""}</div>` : ""}
    ${pk.status !== "none" ? `<div class="approve"><label class="check"><input type="checkbox" data-consent> I reviewed every sentence with ${esc(first)}, and ${esc(first)} agrees to send this.</label>
      <button class="btn btn-primary" data-approve disabled>Approve the packet</button></div>` : ""}
  </section>
  <section class="letter-block" aria-labelledby="msg-h"><h2 id="msg-h">Messages to ${esc(first)}</h2>
    <p class="sub">Every message gives the agency's own phone line and a way to stop texts, and never asks for a Social Security number by text.</p>
    <div class="messages">${out.messages.map(msgHTML).join("")}</div>
    ${fu.messages.length ? `<h3>After the documents arrive</h3><div class="messages">${fu.messages.map(msgHTML).join("")}</div>` : ""}
  </section>`;
}

function msgHTML(m) {
  const ch = { sms: "Text message", phone: "Phone script", mail: "Help reading the mailed notice", chw_visit: "Home visit checklist" }[m.channel] || m.channel;
  const body = m.channel === "sms" ? `<p class="bubble">${esc(m.lines.join(" "))}</p>` : `<div class="script">${m.lines.map((l) => `<p>${esc(l)}</p>`).join("")}</div>`;
  return `<article class="msg msg-${m.channel}"><h3>${ch}</h3><p class="sub">${esc(m.why)}</p>${body}</article>`;
}

// ---------------------------------------------------------------- evidence
function evidence(c, t, cid) {
  const rules = outOf(t, "rules"), ext = stageOf(t, "extract"), facts = ext.output.facts;
  const paths = sortedPaths(rules);
  const live = paths.filter((p) => p.status !== "not_met"), rest = paths.filter((p) => p.status === "not_met");
  const factLink = (fid) => {
    const f = facts.find((x) => x.fact_id === fid);
    return f ? docLink(cid, docById(c, f.doc_id), f.quote, `${f.type.replace(/_/g, " ")} (${f.doc_id})`) : "";
  };
  const detail = (f) => Object.entries(f).filter(([k, v]) => !["type", "doc_id", "line", "quote", "fact_id"].includes(k) && v !== null && v !== "")
    .map(([k, v]) => `${k.replace(/_/g, " ")}: ${esc(v)}`).join(", ");
  return `${provenance("rules", "Each pathway is a fixed rule from the policy pack, applied to the facts at the bottom of this page. Rule links open the regulation text.")}
  <section aria-labelledby="live-h"><h2 id="live-h">${live.length ? "Pathways the documents point to" : "No pathway is supported"}</h2>
    ${live.map((p) => `<article class="pathway"><header><h3>${esc(p.name)}</h3>${status(p.status)}</header>
      <p class="sub">${esc(KIND[p.kind] || p.kind)}. Rule: ${ruleLink(S.rules, S.sources, p.rule_id)}</p>
      ${p.reasons.map((r) => `<p>${esc(r)}</p>`).join("")}
      ${p.evidence.length ? `<p class="sub">Evidence: ${p.evidence.map(factLink).filter(Boolean).join(", ")}</p>` : ""}</article>`).join("") || `<p>None of the ${paths.length} pathways matched the documents.</p>`}
  </section>
  <details class="rest"><summary>${rest.length} other pathways checked and not supported</summary>
    <table class="table"><thead><tr><th>Pathway</th><th>Why not</th><th>Rule</th></tr></thead><tbody>
    ${rest.map((p) => `<tr><td>${esc(p.name)}<span class="sub">${esc(KIND[p.kind] || p.kind)}</span></td><td>${p.reasons.map(esc).join(" ")}</td><td>${ruleLink(S.rules, S.sources, p.rule_id)}</td></tr>`).join("")}
    </tbody></table></details>
  ${rules.interpretations.length ? `<section aria-labelledby="int-h"><h2 id="int-h">What the doctor's letters say about work</h2>
    ${rules.interpretations.map((i) => `<article class="pathway"><header><h3>${esc(docLabel(t, docById(c, i.doc_id)))} (${esc(i.doc_id)})</h3>
      <span class="pill pill-${i.work_impact === "explicit" ? "ok" : "warn"}">${{ explicit: "States the impact on work", vague: "Only hints at an impact", absent: "Doesn't mention work" }[i.work_impact] || esc(i.work_impact)}</span></header>
      <p class="sub">Read by ${i.engine === "llm" ? "an AI model, which must quote the line it relied on" : "keyword rules"}.</p>
      ${i.impact_quote ? `<blockquote>${esc(i.impact_quote)}</blockquote>` : ""}${i.missing_statement ? `<p>Missing: ${esc(i.missing_statement)}</p>` : ""}</article>`).join("")}</section>` : ""}
  <section aria-labelledby="facts-h"><h2 id="facts-h">Facts read from the documents</h2>
    ${provenance(ext.engine === "llm" ? "ai" : "rules", ext.engine === "llm" ? `Extracted by an AI model (${esc(modelNames(ext).join(", "))}). Any fact whose quote isn't word for word in the document is dropped${ext.output.ungrounded_dropped.length ? `; ${ext.output.ungrounded_dropped.length} were dropped this run` : ""}.` : "Extracted by pattern rules. Every fact quotes its document line.")}
    <table class="table"><thead><tr><th>Fact</th><th>Details</th><th>Quote</th></tr></thead><tbody>
    ${facts.map((f) => `<tr><td>${esc(f.type.replace(/_/g, " "))}<span class="sub">${docLink(cid, docById(c, f.doc_id), f.quote, f.doc_id)}</span></td><td>${detail(f)}</td><td class="quote">${esc(f.quote)}</td></tr>`).join("")}
    </tbody></table></section>`;
}

// ---------------------------------------------------------------- agents
function agents(c, t, cid, _params, run) {
  const stages = run ? run.stages.filter((s) => s.record).map((s) => s.record) : t.stages;
  const ver = !run && t ? outOf(t, "verify") : null;
  const sum = !run && t ? t.summary : null;
  return `${provenance("rules", "Every agent's input, output and engine, in the order they ran. Rules handle thresholds, dates and deadlines; AI models read documents, draft and translate, and a verifier checks every drafted sentence.")}
  ${sum ? `<dl class="stats stats-row">
    <div><dt>AI calls</dt><dd>${sum.llm_calls}</dd></div>
    <div><dt>Total time</dt><dd>${sum.latency_ms < 1000 ? `${sum.latency_ms} ms (saved responses)` : `${(sum.latency_ms / 1000).toFixed(1)} s`}</dd></div>
    <div><dt>Cost</dt><dd>$${sum.cost_usd.toFixed(4)}</dd></div>
    <div><dt>Mode</dt><dd>${esc(t.mode)}</dd></div>
    <div><dt>Policy used by this run</dt><dd>${esc(S.packs.find((p) => p.id === sum.pack)?.name || sum.pack)}</dd></div></dl>` : ""}
  <ol class="stage-list">${stages.map((r) => `<li class="stage">
    <div class="stage-head"><h3>${esc(r.label)}</h3><span class="engine engine-${esc(r.engine.split("+")[0])}">${esc(ENGINE[r.engine] || r.engine)}</span>
      <span class="sub">${r.ms} ms${r.llm_calls.length ? `, ${r.llm_calls.length} AI call${r.llm_calls.length > 1 ? "s" : ""}${r.cached_calls ? ` (${r.cached_calls} saved)` : ""}: ${esc(modelNames(r).join(", "))}` : ""}</span></div>
    <p>${esc(r.desc)}</p>
    ${r.note ? `<p class="fallback">Fell back to rules: ${esc(r.note)}</p>` : ""}
    <details><summary>Show the raw output</summary><pre class="raw">${esc(JSON.stringify(r.output, null, 1))}</pre></details></li>`).join("")}</ol>
  ${ver ? `<section id="verifier" aria-labelledby="ver-h"><h2 id="ver-h">Verifier log</h2>
    <p>${ver.stats.claims} drafted sentences checked: ${ver.stats.removed} removed, ${ver.stats.flagged} flagged. Checks: the quote is word for word in the document, the rule exists, every number appears in the support, no wording that decides eligibility${stageOf(t, "verify").engine.includes("llm") ? ", and an AI check that each quote supports its sentence" : ""}.</p>
    ${ver.removed.map((r) => `<div class="log log-removed"><p><strong>Removed</strong> from the ${esc(r.where)}: ${esc(r.text)}</p><p class="sub">${r.reasons.map(esc).join("; ")}</p></div>`).join("")}
    ${ver.flagged.map((r) => `<div class="log log-flagged"><p><strong>Flagged</strong> in the ${esc(r.where)}: ${esc(r.text)}</p><p class="sub">${r.reasons.map(esc).join("; ")}</p></div>`).join("")}
    ${!ver.removed.length && !ver.flagged.length ? "<p>Every sentence had an exact quote or a valid rule behind it.</p>" : ""}</section>` : ""}`;
}
