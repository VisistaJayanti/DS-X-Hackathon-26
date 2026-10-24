// Coverage Keeper UI (vanilla JS, no build step)
const S = { status: null, cases: [], caseData: null, trace: null, pack: "masshealth_ce_2027", packData: null, packs: [] };
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const api = (p) => fetch(p).then((r) => r.json());
const LANG_NAMES = { en: "English", es: "Spanish", pt: "Portuguese", ht: "Haitian Creole", vi: "Vietnamese", zh: "Chinese" };
const STATUS_LABEL = { flagged: "Flagged", contacted: "Contacted", documents_received: "Docs received", packet_ready: "Packet ready", submitted: "Submitted" };
const PSTAT = { met: ["ok", "supported"], insufficient: ["warn", "needs evidence"], not_met: ["grey", "not supported"] };

function tab(name) {
  document.querySelectorAll("#tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.id === "tab-" + name));
  if (name === "eval") loadEval();
  if (name === "packs") renderPacks();
}
document.querySelectorAll("#tabs button").forEach((b) => (b.onclick = () => tab(b.dataset.tab)));

async function init() {
  S.status = await api("/api/status");
  $("#status").textContent = `mode: ${S.status.mode}${S.status.api_key ? "" : " (no API key: cached/deterministic)"} · as of ${S.status.as_of}`;
  $("#lang").innerHTML = Object.entries(S.status.languages).map(([k, v]) => `<option value="${k}">${v}</option>`).join("");
  S.packs = await api("/api/packs");
  await loadPack(S.pack);
  S.cases = await api("/api/cases");
  $("#case-select").innerHTML = S.cases.map((c) => `<option value="${c.case_id}">${c.case_id} · ${esc(c.title)} [${c.split}]</option>`).join("");
  $("#case-select").onchange = () => openCase($("#case-select").value, false);
  $("#run").onclick = run;
  await loadPlan();
  const m = location.hash.match(/autorun=(\w+)/);
  if (m) { await openCase(m[1]); run(); }
}
window.addEventListener("error", (e) => {
  document.body.insertAdjacentHTML("afterbegin", `<div class="removed" id="jserr">JS error: ${esc(e.message)} (${esc(e.filename)}:${e.lineno})</div>`);
});

async function loadPack(id) {
  S.pack = id;
  S.packData = await api("/api/packs/" + id);
  S.rules = Object.fromEntries(S.packData.rulebook.rules.map((r) => [r.id, r]));
  S.sources = S.packData.rulebook._meta.sources;
}

// ------------------------------------------------------------------ plan view
async function loadPlan() {
  const p = await api("/api/plan");
  const r = p.retention;
  $("#kpis").innerHTML = [
    ["Members on roster", r.members], ["Flagged (top-" + p.top_k + ")", r.flagged], ["On track (packet ready / submitted)", r.on_track],
    ["Still at risk", r.at_risk_unresolved], ["Annual revenue on track*", "$" + r.annual_revenue_on_track_usd.toLocaleString()],
  ].map(([l, v]) => `<div class="kpi"><div class="v">${v}</div><div class="l">${l}</div></div>`).join("");
  $("#plan-note").textContent = "* " + r.note.replace("PMPM", `$${r.assumed_pmpm_usd} PMPM`);
  $("#pipelinebar").innerHTML = Object.entries(p.pipeline).map(([k, v]) => `<div>${STATUS_LABEL[k]}<b>${v}</b></div>`).join("");
  const rows = p.rows.slice(0, 60);
  $("#roster").outerHTML = `<div class="scroll"><table class="tbl" id="roster"><tr><th>#</th><th>Member</th><th>Lang</th><th>Risk</th><th>Top reasons</th><th>Due in</th><th>Status</th></tr>
    ${rows.map((x) => `<tr class="${x.case_id ? "click" : ""} ${x.member_id === "M0001" ? "hl" : ""}" ${x.case_id ? `onclick="openCase('${x.case_id}')"` : ""}>
      <td>${x.rank}</td><td><b>${esc(x.name)}</b><div class="muted small">${x.member_id} · ${esc(x.city)} · ${x.age}${x.case_id ? " · case " + x.case_id : ""}</div></td>
      <td>${LANG_NAMES[x.language] || x.language}</td>
      <td><b>${x.score}</b><div class="bar"><i style="width:${Math.min(100, x.score * 8)}%"></i></div></td>
      <td><ul class="reasons">${x.reasons.map((q) => `<li>${esc(q.text)} <span class="muted">+${q.points}</span></li>`).join("")}</ul></td>
      <td>${x.days_left == null ? "-" : x.days_left + " d"}</td>
      <td>${x.flagged ? `<span class="badge ${x.status === "submitted" || x.status === "packet_ready" ? "ok" : ""}">${STATUS_LABEL[x.status]}</span>` : '<span class="muted small">not flagged</span>'}</td></tr>`).join("")}
    </table></div>`;
  $("#maria-timeline").innerHTML = p.maria_timeline.map((e) => `<li><b>Day ${e.day}</b> ${esc(e.event)}</li>`).join("");
  const o = p.outcomes;
  $("#outcomes").innerHTML = `
    <div class="kpi out retain"><div class="l">RETAIN</div><div class="v">${o.retained_on_track}</div><div class="l">at-risk members on track to keep coverage</div></div>
    <div class="kpi out recover"><div class="l">RECOVER</div><div class="v">${o.recovered_on_track} <span class="muted small">of ${o.recoverable_open}</span></div><div class="l">dropped for paperwork, still inside the reconsideration window</div></div>
    <div class="kpi out transition"><div class="l">TRANSITION</div><div class="v">${o.transitioned_handoff_done} <span class="muted small">of ${o.transitioned_handoff_done + o.transition_pending}</span></div><div class="l">likely to lose eligibility, handed off to next coverage</div></div>
    <div class="muted small" style="grid-column:1/-1">${esc(o.note)}</div>`;
  const click = (x) => (x.case_id ? `class="click" onclick="openCase('${x.case_id}')"` : "");
  $("#recover-group").innerHTML = `<table class="tbl"><tr><th>Member</th><th>Dropped</th><th>Reason</th><th>Window ends</th><th>Status</th></tr>
    ${p.recover.map((x) => `<tr ${click(x)}><td><b>${esc(x.name)}</b><div class="muted small">${x.member_id} · ${LANG_NAMES[x.language] || x.language}${x.case_id ? " · case " + x.case_id : ""}</div></td>
      <td>${x.termination_date}</td><td class="small">${esc(x.reason || "")}</td>
      <td>${x.window_ends}<div><b class="${x.days_left < 0 ? "bad-t" : x.days_left <= 21 ? "warn-t" : "ok-t"}">${x.days_left < 0 ? "closed " + -x.days_left + " d ago" : x.days_left + " days left"}</b></div></td>
      <td><span class="badge ${x.recoverable ? (x.status === "packet_ready" || x.status === "submitted" ? "ok" : "") : "bad"}">${STATUS_LABEL[x.status] || x.status}</span></td></tr>`).join("")}</table>`;
  $("#transition-group").innerHTML = `<table class="tbl"><tr><th>Member</th><th>Why</th><th>Coverage ends</th><th>Enrol by (no gap) / window closes</th><th>Hand-off</th></tr>
    ${p.transition.map((x) => `<tr ${click(x)}><td><b>${esc(x.name)}</b><div class="muted small">${x.member_id} · ${LANG_NAMES[x.language] || x.language}${x.case_id ? " · case " + x.case_id : ""}</div></td>
      <td class="small">${esc(x.trigger)}</td><td>${x.coverage_end || "-"}</td><td>${x.avoid_gap_by || "-"} / ${x.window_closes || "-"}</td>
      <td>${x.handoff_done ? '<span class="badge ok">done</span>' : '<span class="badge warn">pending</span>'}</td></tr>`).join("")}</table>`;
}

// ------------------------------------------------------------------ case view
async function openCase(cid, switchTab = true) {
  if (switchTab) tab("case");
  $("#case-select").value = cid;
  S.caseData = await api("/api/cases/" + cid);
  S.activeDoc = null; S.docMode = null;
  S.trace = null;
  const m = S.caseData.member;
  $("#lang").value = m.language || "en";
  $("#case-meta").innerHTML = `${esc(m.name)} · age ${m.age} · prefers ${LANG_NAMES[m.language] || m.language} · ${esc(m.household || "")}
    · notice received ${m.notice_received_date} · review months ${(m.lookback_months || []).join(", ")}
    ${cid === "C46" ? '<span class="badge warn">illustrative composite</span>' : '<span class="badge grey">synthetic</span>'}`;
  renderDocs();
  $("#stagelist").innerHTML = '<p class="muted">Press "Run agents" to watch each agent work.</p>';
  $("#results").innerHTML = "";
}

function renderDocs(hl) {
  const docs = S.caseData.documents;
  const types = S.trace ? Object.fromEntries(stageOut("intake").documents.map((d) => [d.doc_id, d.doc_type])) : {};
  const active = [hl?.doc_id, S.activeDoc].find((id) => id && docs.some((d) => d.doc_id === id)) || docs[0].doc_id;
  S.activeDoc = active;
  $("#doclist").innerHTML = docs.map((d) => `<div class="doc-item ${d.doc_id === active ? "active" : ""}" onclick="showDoc('${d.doc_id}')">
    <span><b>${d.doc_id}</b> ${esc(d.filename)}</span>${types[d.doc_id] ? `<span class="badge">${types[d.doc_id]}</span>` : ""}</div>`).join("");
  const doc = docs.find((d) => d.doc_id === active);
  if (hl) S.docMode = "text";
  const mode = doc.image ? (S.docMode || "original") : "text";
  $("#docmode").innerHTML = doc.image ? `<button class="ghost ${mode === "original" ? "on" : ""}" onclick="S.docMode='original';renderDocs()">Original document</button>
    <button class="ghost ${mode === "text" ? "on" : ""}" onclick="S.docMode='text';renderDocs()">Extracted text (what the agents read)</button>
    <a class="small" href="${doc.pdf}" target="_blank">open PDF</a>` : "";
  $("#docimg").innerHTML = mode === "original" ? `<img src="${doc.image}" alt="${esc(doc.filename)}">` : "";
  $("#docview").style.display = mode === "original" ? "none" : "block";
  const q = hl?.quote ? hl.quote.toLowerCase().replace(/\s+/g, " ") : null;
  $("#docview").innerHTML = doc.text.split("\n").map((l, i) => {
    const hit = q && (l.toLowerCase().replace(/\s+/g, " ").includes(q.slice(0, 40)) || (hl.line === i + 1));
    return `<span class="${hit ? "hit" : ""}"><span class="ln">${i + 1}</span>${esc(l)}</span>`;
  }).join("\n");
  const hitEl = $("#docview .hit");
  if (hitEl) hitEl.scrollIntoView({ block: "center", behavior: "smooth" });
}
function showDoc(id, quote, line) { S.activeDoc = id; if (!quote && !line) S.docMode = "original"; renderDocs(quote || line ? { doc_id: id, quote, line } : null); }

const stageOut = (k) => S.trace?.stages.find((s) => s.key === k)?.output;

function run() {
  if (!S.caseData) return;
  $("#run").disabled = true;
  $("#results").innerHTML = "";
  $("#stagelist").innerHTML = "";
  const params = new URLSearchParams({ lang: $("#lang").value, verifier: $("#verifier").checked ? 1 : 0, engine: $("#engine").value, pack: S.pack });
  const es = new EventSource(`/api/run/${S.caseData.case_id}?${params}`);
  const q = [];
  let timer = null;
  const pump = () => {
    if (!q.length) { timer = null; return; }
    handle(q.shift());
    timer = setTimeout(pump, 220); // pace events so the audience can follow each agent
  };
  es.onmessage = (e) => { q.push(JSON.parse(e.data)); if (!timer) pump(); };
  es.onerror = () => es.close();
  function handle(ev) {
    if (ev.event === "start") {
      $("#stagelist").insertAdjacentHTML("beforeend", `<div class="stage running" id="st-${ev.stage}"><div class="row"><span class="dot"></span><span class="name">${ev.label}</span><span class="desc">working…</span></div></div>`);
    } else if (ev.event === "done") {
      const r = ev.record;
      const el = $("#st-" + ev.stage);
      el.className = "stage done";
      const llm = r.llm_calls.length ? `${r.llm_calls.length} LLM call(s)${r.cached_calls ? `, ${r.cached_calls} cached` : ""} · ${r.llm_calls.map((c) => c.model.replace("claude-", "")).join(", ")}` : "";
      el.innerHTML = `<div class="row"><span class="dot"></span><span class="name">${r.label}</span><span class="desc">${esc(r.desc)}</span>
        <span class="badge ${r.engine.includes("llm") ? "" : "grey"}">${r.engine}</span><span class="muted small">${r.ms} ms${r.cost ? " · $" + r.cost.toFixed(4) : ""}</span>
        <button class="ghost" onclick="this.closest('.stage').classList.toggle('open')">inspect</button></div>
        <div class="muted small">${summarize(r)}${llm ? " · " + llm : ""}${r.note ? ` · <i>fallback: ${esc(r.note)}</i>` : ""}</div>
        <pre>${esc(JSON.stringify(r.output, null, 1))}</pre>`;
    } else if (ev.event === "trace") {
      S.trace = ev.trace;
      renderDocs();
      renderResults();
      $("#run").disabled = false;
      es.close();
    } else if (ev.event === "error") {
      $("#stagelist").insertAdjacentHTML("beforeend", `<div class="removed">Error: ${esc(ev.error)}</div>`);
      $("#run").disabled = false;
      es.close();
    }
  }
}

function summarize(r) {
  const o = r.output;
  switch (r.key) {
    case "risk": return o.walk_in ? o.note : `risk score ${o.score} · ${o.reasons.length} reasons`;
    case "outreach": return `${o.variant || "retain"} message · channels: ${o.channels.join(", ")}`;
    case "intake": return o.documents.map((d) => `${d.doc_id}=${d.doc_type}`).join(", ");
    case "extract": return `${o.facts.length} grounded facts${o.ungrounded_dropped.length ? `, ${o.ungrounded_dropped.length} ungrounded dropped` : ""}`;
    case "rules": return `${o.pathways.length} pathways checked · leading: ${o.ranking.slice(0, 2).join(", ")}`;
    case "gaps": return `${o.gaps.length} gap(s) · due ${o.deadline?.due} (${o.deadline?.days_left} days)`;
    case "followup": return `${o.messages.length} follow-up message(s)`;
    case "outcome": return `${o.outcome.toUpperCase().replace("_", " ")}${o.key_date ? " · key date " + o.key_date : ""}`;
    case "draft": return `packet: ${o.packet.status} · request letter: ${o.request ? "yes" : "no"} · member sentences: ${o.member_en.length}`;
    case "verify": return `${o.stats.claims} claims checked · ${o.stats.removed} removed · ${o.stats.flagged} flagged`;
    case "translate": return `member explanation in ${LANG_NAMES[o.language] || o.language}`;
  }
  return "";
}

function ruleChip(rid) {
  const r = S.rules[rid];
  if (!r) return rid ? `<span class="cite rule">${esc(rid)}</span>` : "";
  const src = S.sources[r.source];
  return `<a class="cite rule" href="${r.url || src.url}" target="_blank" title="${esc(r.cite + ": " + r.quote)}">${esc(r.cite)}</a>${r.needs_confirmation ? ' <span class="badge warn" title="' + esc(r.confirmation_note || "") + '">needs confirmation</span>' : ""}`;
}
S.cites = [];
function factChip(c) {
  if (!c.doc_id) return "";
  S.cites.push({ doc_id: c.doc_id, quote: c.quote || "" });
  return `<span class="cite" onclick="openCite(${S.cites.length - 1})">${esc(c.doc_id)} &#8599;</span>`;
}
function openCite(i) {
  const c = S.cites[i];
  showDoc(c.doc_id, c.quote);
  document.querySelector(".docs").scrollIntoView({ behavior: "smooth" });
}
function claimHTML(c) {
  const text = c.kind === "fact" ? esc(c.text) : esc(c.text);
  return `<div class="claim"><span class="badge grey">${c.kind}</span> ${text} ${factChip(c)} ${c.rule_id ? ruleChip(c.rule_id) : ""}</div>`;
}

function renderResults() {
  S.cites = [];
  const t = S.trace, rules = stageOut("rules"), gaps = stageOut("gaps"), out = stageOut("outreach"), fu = stageOut("followup");
  const ver = stageOut("verify"), fin = t.final, sum = t.summary;
  const paths = [...rules.pathways].sort((a, b) => (rules.ranking.indexOf(a.pathway) + 1 || 99) - (rules.ranking.indexOf(b.pathway) + 1 || 99));
  const oc = stageOut("outcome") || { outcome: "retain" };
  const dl = oc.outcome === "retain" ? gaps.deadline : oc.deadline;
  let h = "";
  const OC = { retain: ["RETAIN", "Keep this member covered: answer the notice before the deadline."],
    recover: ["RECOVER", "Dropped for paperwork and still inside the reconsideration window: send the missing papers; a new application may not be needed."],
    recover_expired: ["RECOVER: WINDOW CLOSED", "The reconsideration window has passed: help the member apply again (and look at next coverage if needed)."],
    transition: ["TRANSITION", "Evidence suggests the member may no longer qualify. Hand off to the right next coverage before a gap opens. The agency decides; a navigator confirms."] };
  h += `<div class="card full outcome-banner ${oc.outcome}"><span class="ob-tag">${OC[oc.outcome][0]}</span> <b>${esc(OC[oc.outcome][1])}</b>
    <div class="muted small">${(oc.reasons || []).map(esc).join(" ")}</div></div>`;
  if (oc.transition && (oc.outcome === "transition" || oc.outcome === "recover_expired")) {
    const tp = oc.transition, w = tp.window || {};
    h += `<div class="card full"><h2>Transition plan: next coverage without a gap</h2>
      <p><b>Why:</b> ${esc(tp.trigger_label)} ${ruleChip(tp.trigger_rule_id)}${tp.coverage_end ? ` · coverage expected to end <b>${tp.coverage_end}</b>` : ""}</p>
      ${w.closes ? `<p><b>Enrol by ${w.avoid_gap_by}</b> to avoid a gap · window opens ${w.opens}, closes <b>${w.closes}</b> ${ruleChip(w.rule_id)}${w.advance_rule_id ? " " + ruleChip(w.advance_rule_id) : ""}</p>` : ""}
      <h3>Options (listed without preference; the member chooses)</h3>
      ${tp.options.map((o) => `<div class="claim">• <b>${esc(o.name)}</b>: ${esc(o.contact)} ${o.rule_id ? ruleChip(o.rule_id) : '<span class="badge warn">needs confirmation</span>'}</div>`).join("")}
      <h3>Documents to have ready</h3><ul>${tp.documents.map((d) => `<li>${esc(d)}</li>`).join("")}</ul>
      <h3>Warm hand-off note for a navigator</h3><div class="letter small">${esc(tp.handoff_note)}</div>
      <p class="muted small">${esc(tp.neutral_routing_note)}</p></div>`;
  }
  h += `<div class="card"><h2>Likely pathway</h2>
    ${sum.best_pathway === "NONE" ? '<p><span class="badge bad">No supported pathway</span> The documents do not support any pathway. Do not invent one: review exemptions with the member and refer to resources.</p>' +
      gaps.resources.map((r) => `<div><a href="${r.url}" target="_blank">${esc(r.name)}</a></div>`).join("")
      : `<p style="font-size:16px"><b>${esc(paths[0].name)}</b> <span class="badge ${PSTAT[paths[0].status][0]}">${PSTAT[paths[0].status][1]}</span></p>
         <p class="muted">Evidence suggests this pathway; the agency decides. ${sum.evidence_sufficient ? "Documents look complete." : "Evidence is incomplete — see gaps."}</p>`}
    <h3>${oc.outcome === "retain" ? "Deadline" : esc((dl && dl.label) || "Deadline")}</h3>${dl && dl.due ? `<div class="deadline ${dl.urgency}">${dl.days_left < 0 ? "Closed " + -dl.days_left + " days ago" : dl.days_left + " days left"}</div>
      <div class="muted">${oc.outcome === "retain" ? `Due ${dl.due} (notice received ${dl.notice_received} + ${S.packData.program.response_window_days} days)` : `${oc.outcome === "transition" ? "Window closes" : "Ends"} ${dl.due}${dl.avoid_gap_by ? ` · enrol by ${dl.avoid_gap_by} to avoid a gap` : ""}`} ${ruleChip(dl.rule_id)}</div>` : "No deadline"}
  </div>`;
  h += `<div class="card"><h2>Gaps &amp; fixes</h2>${gaps.gaps.length ? gaps.gaps.map((g) => `<div class="claim"><span class="badge warn">${g.code}</span>
      <b>${esc(g.detail)}</b><div>${esc(g.fix)}</div><div class="muted small">Ask: ${g.ask}${g.pathway ? " · for " + g.pathway : ""}</div></div>`).join("")
    : '<p class="muted">No gaps found for the leading pathway.</p>'}</div>`;
  h += `<div class="card full"><h2>Every pathway checked</h2><table class="tbl"><tr><th>Pathway</th><th>Result</th><th>Why</th><th>Rule</th></tr>
    ${paths.map((p) => `<tr><td><b>${esc(p.name)}</b><div class="muted small">${p.kind}</div></td><td><span class="badge ${PSTAT[p.status][0]}">${PSTAT[p.status][1]}</span></td>
      <td>${p.reasons.map(esc).join("<br>")}${p.evidence.length ? `<div class="muted small">evidence: ${p.evidence.join(", ")}</div>` : ""}</td><td>${ruleChip(p.rule_id)}</td></tr>`).join("")}</table>
    ${rules.interpretations.length ? `<h3 style="margin-top:10px">Clinician-letter interpretation</h3>` + rules.interpretations.map((i) =>
      `<div class="claim"><b>${i.doc_id}</b> · ${i.engine} · category: ${i.qualifying_category} · work impact: <span class="badge ${i.work_impact === "explicit" ? "ok" : "warn"}">${i.work_impact}</span>
       ${i.impact_quote ? `“${esc(i.impact_quote)}”` : ""} ${i.missing_statement ? `<div class="muted small">Missing: ${esc(i.missing_statement)}</div>` : ""}</div>`).join("") : ""}</div>`;
  h += `<div class="card"><h2>Outreach (${LANG_NAMES[out.messages[0]?.language] || ""})</h2>
    ${out.messages.map(msgHTML).join("")}<h3>Follow-up after documents</h3>${fu.messages.length ? fu.messages.map(msgHTML).join("") : '<p class="muted">Nothing further needed from the member.</p>'}
    <p class="muted small">${esc(out.out_of_scope)}</p></div>`;
  h += `<div class="card"><h2>Member explanation · ${LANG_NAMES[fin.member.language]}</h2><div class="letter">${fin.member.sentences.map((s) => `<p title="${esc(s.en)}">${esc(s.text)}</p>`).join("")}</div>
    <p class="muted small">Translation engine: ${t.stages.find((s) => s.key === "translate").engine}. Hover a sentence for the verified English. Machine-drafted translations need native-speaker review.</p></div>`;
  const pk = fin.packet;
  h += `<div class="card full"><h2>Response packet to ${esc(S.packData.program.agency)} <span class="badge ${pk.status === "ready" ? "ok" : pk.status === "hold" ? "warn" : "grey"}">${pk.status === "ready" ? "ready for review" : pk.status === "hold" ? "hold: waiting for missing evidence" : "no packet"}</span></h2>
    ${pk.sections.map((s) => `<h3>${esc(s.heading)}</h3>${s.claims.map(claimHTML).join("")}`).join("")}
    ${pk.enclosures ? `<div class="muted small">Enclosures: ${pk.enclosures.map(esc).join(" · ")}</div>` : ""}
    ${pk.status !== "none" ? `<div class="confirm"><label><input type="checkbox" id="confirm-send" onchange="$('#approve').disabled=!this.checked"> I (coordinator/navigator) reviewed every claim with the member and confirm the member consents to sending this.</label>
      <button class="primary" id="approve" disabled onclick="this.textContent='Marked approved (demo: nothing is sent)';this.disabled=true">Approve for sending</button></div>` : ""}</div>`;
  if (fin.request) h += `<div class="card"><h2>${esc(fin.request.title)} <span class="badge">to ${fin.request.to}</span></h2><div class="letter">${fin.request.claims.map(claimHTML).join("")}</div></div>`;
  if (ver) {
    h += `<div class="card ${fin.request ? "" : "full"}"><h2>Verifier log</h2><p>${ver.stats.claims} claims checked · <b>${ver.stats.removed} removed</b> · ${ver.stats.flagged} flagged</p>
      ${ver.removed.map((r) => `<div class="removed"><b>Removed</b> [${r.where}] ${esc(r.text)}<div>${r.reasons.map(esc).join("; ")}</div></div>`).join("")}
      ${ver.flagged.map((r) => `<div class="flagged"><b>Flagged</b> [${r.where}] ${esc(r.text)}<div>${r.reasons.map(esc).join("; ")}</div></div>`).join("")}
      ${!ver.removed.length && !ver.flagged.length ? '<p class="muted">Every claim had an exact quote and/or a valid rule. (Deterministic drafts are grounded by construction; LLM drafts are where the verifier earns its keep — see Evaluation.)</p>' : ""}
      <p class="muted small">Checks: quote present verbatim · rule exists · numbers appear in the support · no eligibility-decision language${t.mode === "live" || stageOut("verify") && t.stages.find((s) => s.key === "verify").engine.includes("llm") ? " · LLM entailment" : ""}.</p></div>`;
  } else {
    h += `<div class="card"><h2>Verifier log</h2><p><span class="badge bad">Verifier OFF</span> Drafts are shown unchecked (ablation mode).</p></div>`;
  }
  h += `<div class="card full muted small">Run: pack <b>${sum.pack}</b> · ${sum.llm_calls} LLM calls · ${sum.latency_ms} ms · $${sum.cost_usd.toFixed(4)} · engines: ${Object.entries(sum.engines).map(([k, v]) => k + "=" + v).join(", ")}</div>`;
  $("#results").innerHTML = h;
}

function msgHTML(m) {
  const body = m.channel === "sms" ? `<div class="bubble">${esc(m.lines.join(" "))}</div>` : m.lines.map((l) => `<div>${esc(l)}</div>`).join("");
  const ch = { sms: "Text message", phone: "Phone / voice-agent script", mail: "Mail: notice helper", chw_visit: "Community health worker visit" }[m.channel];
  return `<div class="msg ${m.channel}"><div class="ch">${ch} <span class="muted small" style="text-transform:none">· ${esc(m.why)}${m.engine !== "template" ? " · " + m.engine : ""}</span></div>${body}</div>`;
}

// ------------------------------------------------------------------ evaluation
async function loadEval() {
  const e = await api("/api/eval");
  if (e.available === false) { $("#eval").innerHTML = '<div class="card">No results yet. Run <code>python eval/run_eval.py</code>.</div>'; return; }
  const pct = (x) => (x == null ? "–" : (100 * x).toFixed(0) + "%");
  const runs = e.runs;
  let h = `<div class="card"><h2>Evaluation</h2><p class="muted">${esc(e.note)}</p>
    <table class="tbl"><tr><th>Run</th><th>Split</th><th>n</th><th>Pathway top-1</th><th>Pathway top-2</th><th>Sufficiency acc.</th><th>Gap precision</th><th>Gap recall</th><th>Retain/Recover/Transition</th><th>Key date</th><th>Transition told "still eligible"</th><th>Unsupported claims</th><th>Latency / case</th><th>Cost / case</th></tr>
    ${runs.map((r) => `<tr><td><b>${esc(r.name)}</b></td><td>${r.split}</td><td>${r.n}</td><td>${pct(r.top1)}</td><td>${pct(r.top2)}</td><td>${pct(r.sufficiency_acc)}</td>
      <td>${pct(r.gap_precision)}</td><td>${pct(r.gap_recall)}</td><td>${pct(r.outcome_acc)}</td><td>${pct(r.key_date_acc)} <span class="muted small">n=${r.key_date_n}</span></td>
      <td>${pct(r.transition_told_eligible_rate)} <span class="muted small">n=${r.transition_n}</span></td><td>${r.unsupported_rate == null ? "–" : pct(r.unsupported_rate) + ` <span class="muted small">(${r.unsupported}/${r.claims})</span>`}</td>
      <td>${r.latency_ms_mean} ms</td><td>$${r.cost_usd_mean.toFixed(4)}</td></tr>`).join("")}</table></div>`;
  if (e.ablation) h += `<div class="card"><h2>Verifier ablation (headline)</h2><p>${esc(e.ablation.summary)}</p></div>`;
  if (e.risk) {
    h += `<div class="card"><h2>Risk flagging (roster of ${e.risk.n}, ${e.risk.positives} labelled would-lose-for-paperwork)</h2>
      <table class="tbl"><tr><th>Method</th>${e.risk.ks.map((k) => `<th>P@${k}</th><th>R@${k}</th>`).join("")}</tr>
      ${e.risk.methods.map((m) => `<tr><td>${esc(m.name)}</td>${m.at.map((a) => `<td>${pct(a.precision)}</td><td>${pct(a.recall)}</td>`).join("")}</tr>`).join("")}</table>
      <p class="muted small">${esc(e.risk.note)}</p></div>`;
  }
  if (e.fairness) {
    for (const [dim, rows] of Object.entries(e.fairness)) {
      h += `<div class="card"><h2>Fairness: by ${dim.replace("_", " ")}</h2><table class="tbl"><tr><th>${dim}</th><th>n</th><th>Top-1</th><th>Gap recall</th><th>Gap precision</th></tr>
        ${rows.map((r) => `<tr><td>${esc(r.group)}</td><td>${r.n}</td><td>${pct(r.top1)}</td><td>${pct(r.gap_recall)}</td><td>${pct(r.gap_precision)}</td></tr>`).join("")}</table></div>`;
    }
  }
  if (e.errors?.length) h += `<div class="card"><h2>Errors (test split, primary run)</h2>${e.errors.map((x) => `<div class="claim"><b>${x.case_id}</b> ${esc(x.title)}<div class="muted small">${esc(x.detail)}</div></div>`).join("")}</div>`;
  $("#eval").innerHTML = h;
}

// ------------------------------------------------------------------ packs
async function renderPacks() {
  const p = S.packData;
  let h = `<div class="card"><h2>Policy packs</h2><p class="muted">All program-specific content lives in a swappable pack: scope, pathways and thresholds, exemptions and evidence, deadlines, document types, notice conventions, languages, cited sources. The agents only read the active pack.</p>
    <label>Active pack for runs: <select id="packsel">${S.packs.map((x) => `<option value="${x.id}" ${x.id === S.pack ? "selected" : ""}>${esc(x.name)}${x.illustrative ? " (ILLUSTRATIVE)" : ""}</option>`).join("")}</select></label></div>`;
  h += `<div class="card"><h2>${esc(p.name)} ${p.illustrative ? '<span class="badge bad">ILLUSTRATIVE: made-up rules</span>' : '<span class="badge ok">cited sources</span>'}</h2>
    <p>${esc(p.summary)}</p><p class="muted">Line of business: ${esc(p.line_of_business)} · ${esc(p.jurisdiction)} · response window ${p.program.response_window_days} days · languages: ${p.languages.join(", ")}</p>
    <h3>Pathways (generic evaluator + parameters)</h3><table class="tbl"><tr><th>Pathway</th><th>Kind</th><th>Evaluator</th><th>Parameters</th><th>Rule</th></tr>
    ${p.pathways.map((w) => `<tr><td>${w.id}</td><td>${w.kind}</td><td><code>${w.evaluator}</code></td><td class="small"><code>${esc(JSON.stringify(w.params))}</code></td><td>${ruleChip(w.rule_id)}</td></tr>`).join("")}</table>
    <h3 style="margin-top:12px">Rulebook</h3><table class="tbl"><tr><th>Rule</th><th>Verbatim source text</th><th>Source</th></tr>
    ${p.rulebook.rules.map((r) => `<tr><td><b>${r.id}</b><div class="small">${esc(r.name)}</div>${r.needs_confirmation ? '<span class="badge warn">needs confirmation</span>' : ""}</td>
      <td class="small">“${esc(r.quote)}”${r.confirmation_note ? `<div class="muted">${esc(r.confirmation_note)}</div>` : ""}</td>
      <td class="small"><a href="${r.url || p.rulebook._meta.sources[r.source].url}" target="_blank">${esc(r.cite)}</a><div class="muted">${r.source_status}</div></td></tr>`).join("")}</table></div>`;
  $("#packs").innerHTML = h;
  $("#packsel").onchange = async (e) => { await loadPack(e.target.value); renderPacks(); };
}

init();
