// Hash router: every page has its own URL, so refresh, Back and shared links work.
//   #/                         Today            #/case/C46[/documents|letters|evidence|agents]
//   #/members?view=&q=&lang=   Members          #/policies  #/safeguards
import { S, boot, onChange } from "./store.js";
import { esc } from "./ui.js";
import * as today from "./pages/today.js";
import * as members from "./pages/members.js";
import * as casePage from "./pages/case.js";
import * as policies from "./pages/policies.js";
import * as safeguards from "./pages/safeguards.js";

const ROUTES = [
  [/^\/?$/, today, "today"],
  [/^\/members$/, members, "members"],
  [/^\/case\/([\w-]+)(?:\/(\w+))?$/, casePage, "case"],
  [/^\/policies$/, policies, "policies"],
  [/^\/safeguards$/, safeguards, "safeguards"],
];
const view = document.getElementById("view");
let current = null;

// "#/case/C46/letters?x=1#packet": the route, its query, and an in-page anchor to scroll to.
function parse() {
  const [route, anchor] = (location.hash.replace(/^#/, "") || "/").split("#");
  const [path, qs] = route.split("?");
  return { path: path || "/", params: new URLSearchParams(qs || ""), anchor };
}

async function render({ keepScroll = false } = {}) {
  const { path, params, anchor } = parse();
  const hit = ROUTES.map(([re, page, nav]) => [path.match(re), page, nav]).find(([m]) => m);
  document.querySelectorAll("[data-nav]").forEach((a) => a.toggleAttribute("aria-current", !!hit && a.dataset.nav === hit[2]));
  if (!hit) { view.innerHTML = `<div class="empty"><h2>That page doesn't exist</h2><p><a href="#/">Go to Today</a></p></div>`; return; }
  const [m, page, nav] = hit;
  const y = window.scrollY;
  current = { page, args: m.slice(1), params, nav, path };
  try {
    await page.render(view, m.slice(1), params);
    if (page.title) document.title = `${page.title(m.slice(1))} | Coverage Keeper`;
  } catch (e) {
    view.innerHTML = `<div class="empty"><h2>This page couldn't load</h2><p>${esc(e.message)}. Check that <code>python server.py</code> is running, then reload.</p></div>`;
  }
  if (keepScroll) window.scrollTo(0, y);
  else if (anchor && document.getElementById(anchor)) document.getElementById(anchor).scrollIntoView();
  else if (!params.get("line")) window.scrollTo(0, 0);
}

window.addEventListener("hashchange", () => render());
// Live run progress: re-render only the case pages of the case being run.
onChange(({ cid } = {}) => { if (current?.nav === "case" && current.args[0] === cid) render({ keepScroll: true }); });

// Legacy deep link used in the README and demo script: #autorun=C46
async function start() {
  await boot();
  const st = S.status;
  const models = [...new Set(Object.values(st.models).map((m) => m.split(":")[0]))];
  document.getElementById("engine-status").innerHTML = st.mode === "live"
    ? `Models: live, ${esc(st.preset)} preset (${esc(models.join(", "))})`
    : st.mode === "replay" ? "Models: saved responses only, rules elsewhere" : "Models: off, rules only";
  const legacy = location.hash.match(/autorun=(\w+)/);
  if (legacy) {
    location.hash = `#/case/${legacy[1]}`;
    const { runCase } = await import("./store.js");
    runCase(legacy[1], {});
  }
  render();
}
start().catch((e) => { view.innerHTML = `<div class="empty"><h2>Coverage Keeper couldn't start</h2><p>${esc(e.message)}. Start the server with <code>python server.py</code> and reload.</p></div>`; });
