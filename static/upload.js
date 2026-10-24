// Upload tab: features 1 (upload + required documents), 2 (policy matching) and 3 (flags + corrections).
const U = { ready: false, caseId: null, match: null, check: null, docs: [], pack: null };
const MATCH_BADGE = { match: ["ok", "good match"], possible: ["warn", "possible match"], no_match: ["grey", "does not fit"] };
const CRIT_BADGE = { pass: ["ok", "ok"], warn: ["warn", "check"], unknown: ["grey", "unknown"], fail: ["bad", "fails"] };
const ALLOWED = [".pdf", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".txt", ".md"];

async function initUpload() {
  if (U.ready) return;
  U.ready = true;
  const meta = await api("/api/countries");
  const opts = '<option value="">Select…</option>' + meta.countries.map((c) => `<option value="${c.code}">${esc(c.name)}</option>`).join("");
  $("#u-nationality").innerHTML = opts;
  $("#u-country").innerHTML = opts;
  $("#u-tier").innerHTML = '<option value="">Select…</option>' + Object.entries(meta.tiers).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("");
  $("#u-language").innerHTML = Object.entries(S.status.languages).map(([k, v]) => `<option value="${k}">${v}</option>`).join("");
  $("#u-tier").onchange = () => { $("#u-notice-wrap").style.display = $("#u-tier").value === "medicaid" ? "" : "none"; };
  $("#u-files").onchange = listFiles;
  $("#u-form").onsubmit = submitUpload;
}

function listFiles() {
  const files = [...$("#u-files").files];
  $("#u-filelist").innerHTML = files.length
    ? files.map((f) => {
        const ok = ALLOWED.some((x) => f.name.toLowerCase().endsWith(x)) && f.size <= 10 * 1024 * 1024;
        return `<div class="doc-item"><span>${esc(f.name)} <span class="muted small">${(f.size / 1024).toFixed(0)} KB</span></span>
          ${ok ? '<span class="badge ok">ready</span>' : '<span class="badge bad">type or size not allowed</span>'}</div>`;
      }).join("")
    : '<div class="flagged">No documents selected. You can still check the profile, but every required document will be flagged as missing.</div>';
}

async function submitUpload(e) {
  e.preventDefault();
  const files = [...$("#u-files").files];
  if (!$("#u-consent").checked) { $("#u-msg").innerHTML = '<div class="removed">Please confirm the consent box first.</div>'; return; }
  const bad = files.filter((f) => !ALLOWED.some((x) => f.name.toLowerCase().endsWith(x)) || f.size > 10 * 1024 * 1024);
  if (bad.length) { $("#u-msg").innerHTML = `<div class="removed">Remove these files first: ${bad.map((f) => esc(f.name)).join(", ")}</div>`; return; }
  const profile = {
    name: $("#u-name").value.trim(), dob: $("#u-dob").value, nationality: $("#u-nationality").value,
    country: $("#u-country").value, region: $("#u-region").value.trim(), tier: $("#u-tier").value,
    coverage_start: $("#u-start").value, coverage_end: $("#u-end").value, language: $("#u-language").value,
    notice_received_date: $("#u-tier").value === "medicaid" ? $("#u-notice").value : "",
  };
  const fd = new FormData();
  fd.append("profile", JSON.stringify(profile));
  files.forEach((f) => fd.append("files", f));
  $("#u-submit").disabled = true;
  $("#u-msg").innerHTML = '<p class="muted">Reading documents, encrypting and checking policies…</p>';
  try {
    const r = await fetch("/api/upload", { method: "POST", body: fd });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || r.statusText);
    U.caseId = data.case_id; U.match = data.match; U.check = data.check; U.pack = data.check.pack;
    U.docs = (await api("/api/cases/" + U.caseId)).documents;
    Secure.setViewer(profile.name || "Coverage Keeper user");
    $("#u-msg").innerHTML = `<p class="muted small">Saved as case <b>${U.caseId}</b>, encrypted on the server. Only the text read from your files is kept.</p>`;
    renderUpload();
    S.cases = await api("/api/cases");
    $("#case-select").innerHTML = S.cases.map((c) => `<option value="${c.case_id}">${c.case_id} · ${esc(c.title)} [${c.split}]</option>`).join("");
  } catch (err) {
    $("#u-msg").innerHTML = `<div class="removed">Upload failed: ${esc(err.message)}</div>`;
  } finally {
    $("#u-submit").disabled = false;
  }
}

async function choosePack(id) {
  U.pack = id;
  U.check = await api(`/api/check/${U.caseId}?pack=${encodeURIComponent(id)}`);
  renderUpload();
}

function renderUpload() {
  const m = U.match, c = U.check;
  const chosen = m.results.find((r) => r.pack === U.pack) || m.results[0];
  let h = `<div class="card"><div class="card-h"><h2>Policies matched to this member</h2><span class="muted small">age · nationality · country · timeline · tier</span></div>
    ${m.results.map((r) => `<div class="match ${r.pack === U.pack ? "active" : ""}" onclick="choosePack('${r.pack}')">
      <div class="row"><b>${esc(r.name)}</b>
        <span class="badge ${MATCH_BADGE[r.status][0]}">${MATCH_BADGE[r.status][1]}</span>
        ${r.illustrative ? '<span class="badge bad" title="Made-up rules for the demo">illustrative rules</span>' : '<span class="badge ok">cited rules</span>'}
        <span class="muted small" style="margin-left:auto">score ${r.score}</span></div>
      <div class="crit">${r.criteria.map((x) => `<span class="badge ${CRIT_BADGE[x.status][0]}" title="${esc(x.detail)}">${esc(x.criterion.replace("_", " "))}: ${CRIT_BADGE[x.status][1]}</span>`).join(" ")}</div>
    </div>`).join("")}
    <p class="muted small">Click a policy to check the documents against it. Hover a criterion for the reason.</p></div>`;

  h += `<div class="two"><div class="card grow"><h2>Flags &amp; suggested corrections · ${esc(chosen.name)}</h2>
    <p>${c.counts.errors ? `<span class="badge bad">${c.counts.errors} to fix</span>` : '<span class="badge ok">nothing blocking</span>'}
       ${c.counts.warnings ? `<span class="badge warn">${c.counts.warnings} to check</span>` : ""}</p>
    ${c.flags.length ? c.flags.map((f, i) => `<div class="flag ${f.severity}">
        <div><span class="badge ${f.severity === "error" ? "bad" : "warn"}">${f.severity === "error" ? "fix" : "check"}</span> <b>${esc(f.title)}</b>
          ${f.doc_id ? `<span class="cite" onclick="uShowDoc('${f.doc_id}', ${f.line ?? "null"})">${f.doc_id}${f.line ? " line " + f.line : ""} &#8599;</span>` : ""}
          ${f.rule_id ? uRuleChip(f.rule_id) : ""}</div>
        <div class="muted">${esc(f.detail)}</div>
        ${f.fix ? `<div class="fix"><b>Suggested correction:</b> ${esc(f.fix)}</div>` : ""}
      </div>`).join("") : '<p class="muted">No problems found against this policy.</p>'}
    <p class="muted small">${esc(c.note)}</p></div>

    <div class="card side"><h2>Required documents</h2>
      ${c.required_documents.map((r) => `<div class="req ${r.present ? "ok" : "missing"}">
        <span class="badge ${r.present ? "ok" : "bad"}">${r.present ? "found" : "missing"}</span> ${esc(r.label)}
        ${r.present && r.found_in ? `<span class="cite" onclick="uShowDoc('${r.found_in.doc_id}', ${r.found_in.line ?? "null"})">${r.found_in.doc_id} &#8599;</span>` : ""}
        ${!r.present ? `<div class="muted small">${esc(r.fix)}</div>` : ""}</div>`).join("") || '<p class="muted">This policy lists no required documents.</p>'}
      <div class="actions">
        ${chosen.runnable ? `<button class="primary" onclick="uRunPipeline()">Run full agent pipeline &rarr;</button>` : '<p class="muted small">This policy supports matching and document checks only (no agent pipeline yet).</p>'}
        <button class="ghost danger" onclick="uDelete()">Delete my documents</button>
      </div>
    </div></div>`;

  h += `<div class="card"><h2>Your documents</h2><p class="muted small">${Secure.touch ? "Press and hold a document to view it." : "Documents blur when you leave this tab."} Copying, printing and saving are disabled here.</p>
    <div id="u-doclist"></div><pre id="u-docview" class="docview"></pre></div>`;
  $("#u-results").innerHTML = h;
  uShowDoc(U.docs[0]?.doc_id);
}

function uRuleChip(rid) {
  const r = U.check.rules?.[rid];
  if (!r) return `<span class="cite rule">${esc(rid)}</span>`;
  return `<span class="cite rule" title="${esc(r.cite + ": " + r.quote)}">${esc(r.cite)}</span>${r.needs_confirmation ? ' <span class="badge warn">needs confirmation</span>' : ""}`;
}

function uShowDoc(docId, line) {
  if (!U.docs.length) { $("#u-doclist").innerHTML = '<p class="muted">No documents uploaded.</p>'; $("#u-docview").style.display = "none"; return; }
  const doc = U.docs.find((d) => d.doc_id === docId) || U.docs[0];
  $("#u-doclist").innerHTML = U.docs.map((d) => `<div class="doc-item ${d.doc_id === doc.doc_id ? "active" : ""}" onclick="uShowDoc('${d.doc_id}')">
    <span><b>${d.doc_id}</b> ${esc(d.filename)}</span>${d.text.trim().length < 25 ? '<span class="badge bad">unreadable</span>' : ""}</div>`).join("");
  const view = $("#u-docview");
  view.innerHTML = (doc.text || "(no text could be read from this file)").split("\n")
    .map((l, i) => `<span class="${line === i + 1 ? "hit" : ""}"><span class="ln">${i + 1}</span>${esc(l)}</span>`).join("\n");
  Secure.protect(view);
  const hit = view.querySelector(".hit");
  if (hit) { view.scrollIntoView({ behavior: "smooth", block: "nearest" }); hit.scrollIntoView({ block: "center" }); }
}

async function uRunPipeline() {
  await loadPack(U.pack);
  await openCase(U.caseId);
  run();
}

async function uDelete() {
  if (!confirm("Delete this case and its documents from the server? This can't be undone.")) return;
  await fetch("/api/cases/" + U.caseId, { method: "DELETE" });
  U.caseId = null; U.docs = [];
  $("#u-results").innerHTML = '<div class="card"><p>Deleted. Nothing from this upload is stored any more.</p></div>';
  $("#u-form").reset(); listFiles();
  S.cases = await api("/api/cases");
  $("#case-select").innerHTML = S.cases.map((c) => `<option value="${c.case_id}">${c.case_id} · ${esc(c.title)} [${c.split}]</option>`).join("");
}
