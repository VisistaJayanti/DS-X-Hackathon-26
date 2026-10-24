// Today: what needs doing next, soonest deadline first.
import { S, getPlan } from "../store.js";
import { LANG, MEMBER_STATUS, addDays, dayDiff, daysLeftText, esc, fmtDate, nameHTML, splitName, urgency, windowBar } from "../ui.js";

export const title = () => "Today";

const NEXT_STEP = {
  flagged: "Make first contact: text and call in their language",
  contacted: "Collect their documents (photo by text or a home visit)",
  documents_received: "Run the agents and check what's missing",
  packet_ready: "Review the packet with them and approve it",
};

function tasks(p, asOf, windowDays) {
  const out = [];
  for (const r of p.rows) {
    if (!r.flagged || !NEXT_STEP[r.status]) continue;
    out.push({ tone: "retain", name: r.name, case_id: r.case_id, member_id: r.member_id, meta: `${LANG[r.language] || r.language}, ${r.city}`,
      what: NEXT_STEP[r.status], days: r.days_left, end: r.due, start: r.due && addDays(r.due, -windowDays), endLabel: "Notice due" });
  }
  for (const r of p.recover) {
    if (r.status === "submitted") continue;
    const open = r.days_left >= 0;
    out.push({ tone: open ? "recover" : "closed", name: r.name, case_id: r.case_id, member_id: r.member_id, meta: `${LANG[r.language] || r.language}, dropped ${fmtDate(r.termination_date, asOf)}`,
      what: open ? "Send the missing papers before the reconsideration window closes" : "The window closed: help them apply again",
      days: r.days_left, end: r.window_ends, start: r.termination_date, endLabel: "Window closes" });
  }
  for (const r of p.transition) {
    if (r.handoff_done) continue;
    const end = r.avoid_gap_by || r.window_closes;
    out.push({ tone: "transition", name: r.name, case_id: r.case_id, member_id: r.member_id, meta: `${LANG[r.language] || r.language}, ${r.trigger || "no pathway found"}`,
      what: "Hand off to a navigator to line up the next coverage", days: end ? dayDiff(asOf, end) : null, end, start: end && addDays(end, -60), endLabel: "Enroll by" });
  }
  return out.sort((a, b) => (a.days ?? 9999) - (b.days ?? 9999));
}

export async function render(el) {
  const p = await getPlan();
  const asOf = S.status.as_of;
  const all = tasks(p, asOf, S.packData.program.response_window_days);
  const n = (t) => all.filter((x) => x.tone === t).length;
  const urgent = all.filter((x) => x.days != null && x.days <= 14).length;
  const r = p.retention, o = p.outcomes;
  const d = new Date(asOf + "T12:00:00").toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric", year: "numeric" });

  el.innerHTML = `
  <header class="page-head">
    <h1>Today</h1>
    <p class="dateline">${d}</p>
  </header>
  <p class="lede">${all.length} members need something from you. ${urgent} of them have a deadline within two weeks.</p>
  <div class="today-grid">
    <section aria-labelledby="work-h">
      <div class="section-head"><h2 id="work-h">Next actions, soonest deadline first</h2>
        <p class="legend"><span class="key tone-retain">Keep covered ${n("retain")}</span><span class="key tone-recover">Recover ${n("recover") + n("closed")}</span><span class="key tone-transition">Move to new coverage ${n("transition")}</span></p></div>
      <ol class="tasks">
        ${all.slice(0, 14).map((t) => `
        <li class="task tone-${t.tone}">
          <div class="task-who">${t.case_id ? `<a href="#/case/${t.case_id}">${nameHTML(t.name, { inList: true })}</a>` : `<span>${nameHTML(t.name, { inList: true })}</span>`}
            <span class="task-meta">${esc(t.meta)}</span></div>
          <p class="task-what">${esc(t.what)}</p>
          <div class="task-when is-${urgency(t.days)}">${windowBar({ start: t.start, end: t.end, today: asOf, tone: t.tone, size: "sm", endLabel: t.endLabel })}
            <span>${t.days == null ? "No date" : daysLeftText(t.days)}</span></div>
          ${t.case_id ? `<a class="btn btn-quiet" href="#/case/${t.case_id}">Open case</a>` : `<a class="btn btn-quiet" href="#/members?q=${encodeURIComponent(splitName(t.name).name)}">Find member</a>`}
        </li>`).join("")}
      </ol>
      ${all.length > 14 ? `<p class="more"><a href="#/members">See all ${all.length} on the Members page</a></p>` : ""}
    </section>
    <aside class="today-side">
      <section class="stories" aria-labelledby="stories-h">
        <h2 id="stories-h">Walk through a case</h2>
        <p class="muted">Illustrative composites, not real people.</p>
        <a class="story tone-retain" href="#/case/C46"><b>Maria</b><span>Cares for her mother after a stroke. The doctor's letter doesn't state the disability.</span></a>
        <a class="story tone-recover" href="#/case/C47"><b>Devon</b><span>Dropped 20 days ago because a pay stub never arrived.</span></a>
        <a class="story tone-transition" href="#/case/C50"><b>Kofi</b><span>A new job raised his income above the limit.</span></a>
      </section>
      <section aria-labelledby="plan-h">
        <h2 id="plan-h">Across the plan</h2>
        <dl class="stats">
          <div><dt>Members on the roster</dt><dd>${r.members}</dd></div>
          <div><dt>Flagged as at risk</dt><dd>${r.flagged}</dd></div>
          <div><dt>On track (packet ready or sent)</dt><dd>${r.on_track}</dd></div>
          <div><dt>Recoverable, window still open</dt><dd>${o.recoverable_open}</dd></div>
          <div><dt>Handed off to new coverage</dt><dd>${o.transitioned_handoff_done} of ${o.transitioned_handoff_done + o.transition_pending}</dd></div>
          <div><dt>Yearly revenue kept on track</dt><dd>$${r.annual_revenue_on_track_usd.toLocaleString()}</dd></div>
        </dl>
        <p class="fine">Revenue assumes $${r.assumed_pmpm_usd} per member per month, an illustrative figure. ${esc(o.note)}</p>
      </section>
    </aside>
  </div>`;
}
