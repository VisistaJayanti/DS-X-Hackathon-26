// App state, API access with caching, and agent runs streamed over server-sent events.
// Results are kept per policy pack: the same case can be worked out under several policies.

export const S = {
  status: null, packs: [], pack: "masshealth_ce_2027", packData: null, rules: {}, sources: {},
  cases: [], plan: null,
  caseData: {},   // case_id -> case JSON
  runs: {},       // "<pack>/<case_id>" -> last trace (null when the case has never been run under that pack)
  running: {},    // "<pack>/<case_id>" -> { stages: [{key,label,state,record}], error }
  settings: {},   // case_id -> { lang, engine, verifier }
  impacts: {},    // "<pack>|<base>" -> policy impact on the dataset
};
export const rk = (cid) => `${S.pack}/${cid}`;

const listeners = new Set();
export const onChange = (fn) => listeners.add(fn);
const notify = (detail) => listeners.forEach((fn) => fn(detail));

export async function api(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${r.status} on ${path}`);
  return r.json();
}

export async function boot() {
  const [status, packs, cases] = await Promise.all([api("/api/status"), api("/api/packs"), api("/api/cases")]);
  Object.assign(S, { status, packs, cases });
  let saved = null;
  try { saved = localStorage.getItem("ck-pack"); } catch (e) { /* storage blocked: use the default */ }
  await loadPack(packs.some((p) => p.id === saved) ? saved : status.default_pack || S.pack);
}

export async function loadPack(id) {
  S.packData = await api("/api/packs/" + id);
  S.pack = id;
  S.rules = Object.fromEntries(S.packData.rulebook.rules.map((r) => [r.id, r]));
  S.sources = S.packData.rulebook._meta.sources;
}

// Switch the policy used for case pages and new runs, remember it, and let open pages re-render.
export async function setPack(id) {
  await loadPack(id);
  try { localStorage.setItem("ck-pack", id); } catch (e) { /* not remembered; still switched */ }
  notify({ pack: id });
}

export async function getPlan() { return S.plan || (S.plan = await api("/api/plan")); }

export async function getImpact(pack, base) {
  const key = `${pack}|${base}`;
  return S.impacts[key] || (S.impacts[key] = await api(`/api/policy-impact?pack=${pack}&base=${base}`));
}

export async function getCase(cid) {
  if (!S.caseData[cid]) S.caseData[cid] = await api("/api/cases/" + cid);
  const key = rk(cid);
  if (!(key in S.runs)) S.runs[key] = await api(`/api/cases/${cid}/last-run?pack=${S.pack}`).catch(() => null);
  return S.caseData[cid];
}

export const stageOf = (trace, key) => trace?.stages.find((s) => s.key === key);
export const outOf = (trace, key) => stageOf(trace, key)?.output;

export function runCase(cid, { lang, engine = "auto", verifier = true } = {}) {
  const key = rk(cid);  // the pack is fixed when the run starts
  if (S.running[key]) return;
  const run = (S.running[key] = { stages: [], error: null, started: Date.now() });
  notify({ cid });
  const params = new URLSearchParams({ lang: lang || "", verifier: verifier ? 1 : 0, engine, pack: S.pack });
  const es = new EventSource(`/api/run/${cid}?${params}`);
  es.onmessage = (e) => {
    const ev = JSON.parse(e.data);
    if (ev.event === "start") run.stages.push({ key: ev.stage, label: ev.label, state: "running" });
    else if (ev.event === "done") {
      const s = run.stages.find((x) => x.key === ev.stage);
      if (s) Object.assign(s, { state: "done", record: ev.record });
    } else if (ev.event === "trace") {
      S.runs[key] = ev.trace;
      delete S.running[key];
      es.close();
    } else if (ev.event === "error") {
      run.error = ev.error;
      es.close();
    }
    notify({ cid });
  };
  es.onerror = () => {
    if (S.running[key]) { run.error = run.error || "The connection to the server dropped. Check that python server.py is still running, then run again."; }
    es.close();
    notify({ cid });
  };
}
export function clearRunError(cid) { if (S.running[rk(cid)]?.error) delete S.running[rk(cid)]; }
