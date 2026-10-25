"""Record a walkthrough of the Coverage Keeper website that cuts to under 3 minutes (no audio; talk over it).

Usage: start the app (python server.py, or PORT=8010 python server.py), create or pick a case that has never
been run, then:
    python scripts/record_website.py --url http://127.0.0.1:8010 --case <case id>
Output in demo_video/:
    raw_walkthrough.webm   real time, including the whole live AI run
    walkthrough.mp4        the cut: 1920x1080, under 3 minutes; the live run is sped up, with an on-screen clock
                           that keeps showing the real elapsed time
    timeline.json          when each scene starts in the cut (for the voice-over script)
Requires: pip install playwright imageio-ffmpeg. Uses the installed Microsoft Edge; no browser download.
"""
import argparse
import json
import subprocess
import time
from pathlib import Path

import imageio_ffmpeg
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "demo_video"
VIEW = {"width": 1536, "height": 864}  # recorded at this size, upscaled to 1920x1080 in the cut
TARGET = 175.0  # length of the cut in seconds; must stay under 180

CHROME_JS = """() => {
  if (document.getElementById('ck-cursor')) return;
  const css = document.createElement('style');
  css.textContent = `
    #ck-cursor{position:fixed;left:-40px;top:-40px;width:24px;height:24px;z-index:2147483647;pointer-events:none}
    #ck-ring{position:fixed;left:-80px;top:-80px;width:38px;height:38px;margin:-19px 0 0 -19px;border:3px solid #F2B705;
      border-radius:50%;z-index:2147483646;pointer-events:none;opacity:0}
    #ck-ring.on{animation:ckring .55s ease-out}
    @keyframes ckring{from{opacity:1;transform:scale(.35)}to{opacity:0;transform:scale(1.4)}}
    #ck-card{position:fixed;inset:0;z-index:2147483645;background:#24508F;color:#fff;display:flex;flex-direction:column;
      justify-content:center;padding:0 11vw;font-family:'Atkinson Hyperlegible',system-ui,sans-serif}
    #ck-card h1{font-size:60px;margin:0 0 20px;letter-spacing:-.01em}
    #ck-card p{font-size:25px;line-height:1.45;max-width:31em;margin:0 0 12px;color:#DCE5F2}
    #ck-live{position:fixed;right:26px;bottom:26px;z-index:2147483645;background:#18212B;color:#fff;border-radius:6px;
      padding:12px 18px;font:15px/1.45 'Atkinson Hyperlegible',system-ui,sans-serif}
    #ck-live b{display:block;font-size:16px}
    #ck-live span{font-variant-numeric:tabular-nums;color:#FFE58A;font-size:24px;font-weight:700;margin-left:6px}
  `;
  document.head.appendChild(css);
  const cur = document.createElement('div');
  cur.id = 'ck-cursor';
  cur.innerHTML = '<svg viewBox="0 0 24 24" width="24" height="24"><path d="M3 2l7 19 2.6-7.4L20 11z" fill="#18212B" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/></svg>';
  const ring = document.createElement('div');
  ring.id = 'ck-ring';
  document.body.append(cur, ring);
  addEventListener('mousemove', (e) => { cur.style.left = (e.clientX - 3) + 'px'; cur.style.top = (e.clientY - 2) + 'px'; }, true);
  addEventListener('mousedown', (e) => {
    ring.style.left = e.clientX + 'px'; ring.style.top = e.clientY + 'px';
    ring.classList.remove('on'); void ring.offsetWidth; ring.classList.add('on');
  }, true);
}"""
CARD_JS = """([title, lines]) => {
  const d = document.createElement('div'); d.id = 'ck-card';
  d.innerHTML = '<h1>' + title + '</h1>' + lines.map((l) => '<p>' + l + '</p>').join('');
  document.body.appendChild(d);
}"""
LIVE_JS = """(label) => {
  let el = document.getElementById('ck-live');
  if (!el) { el = document.createElement('div'); el.id = 'ck-live'; document.body.appendChild(el); }
  const t0 = Date.now(), fmt = (s) => Math.floor(s / 60) + ':' + String(Math.floor(s % 60)).padStart(2, '0');
  clearInterval(window.__ckClock);
  const tick = () => { el.innerHTML = '<b>' + label + '</b>Real time<span>' + fmt((Date.now() - t0) / 1000) + '</span>'; };
  tick(); window.__ckClock = setInterval(tick, 250);
}"""
LIVE_DONE_JS = """() => {
  clearInterval(window.__ckClock);
  const el = document.getElementById('ck-live');
  if (el) el.innerHTML = el.innerHTML.replace('Real time', 'Finished in');
}"""


class Recorder:
    def __init__(self, page):
        self.page, self.t0, self.marks = page, time.monotonic(), []

    def mark(self, scene):
        self.marks.append({"scene": scene, "raw": round(time.monotonic() - self.t0, 2)})
        print(f"  {self.marks[-1]['raw']:7.1f}s  {scene}", flush=True)

    def wait(self, secs):
        self.page.wait_for_timeout(int(secs * 1000))

    def has(self, selector):
        return self.page.locator(selector).count() > 0

    def point(self, selector, pause=0.2, steps=16):
        loc = self.page.locator(selector).first
        loc.scroll_into_view_if_needed()
        b = loc.bounding_box()
        self.page.mouse.move(b["x"] + min(b["width"] / 2, 260), b["y"] + min(b["height"] / 2, 22), steps=steps)
        self.wait(pause)

    def click(self, selector, after=0.5):
        self.point(selector, pause=0.12)
        self.page.mouse.down()
        self.page.mouse.up()
        self.wait(after)

    def scroll(self, selector, block="start", secs=1.0):
        self.page.locator(selector).first.evaluate(f"e => e.scrollIntoView({{behavior: 'smooth', block: '{block}'}})")
        self.wait(secs)

    def go(self, hash_, ready, secs=0.6):
        self.page.evaluate(f"location.hash = '{hash_}'")
        self.page.wait_for_selector(ready)
        self.wait(secs)

    def card(self, title, lines, secs):
        self.page.evaluate(CARD_JS, [title, lines])
        self.wait(secs)
        self.page.evaluate("() => document.getElementById('ck-card')?.remove()")


def scenes(r, case_id):
    p = r.page
    # ---------------------------------------------------------------- opening
    r.mark("title")
    r.card("Coverage Keeper", ["AI agents that finish Medicaid renewal paperwork, so eligible members keep their health coverage.",
                               "Hackachusetts 2026. Every member and document in this video is synthetic."], 7)

    # ---------------------------------------------------------------- Today
    r.mark("today")
    r.point(".lede"); r.wait(2.4)
    r.point(".tasks li:nth-child(1) .task-what"); r.wait(1.8)
    r.point(".tasks li:nth-child(1) .task-when"); r.wait(1.6)
    r.point(".legend"); r.wait(1.4)
    r.point(".stories .story:nth-of-type(1)"); r.wait(1.6)
    r.point(".today-side .stats"); r.wait(2.2)

    # ---------------------------------------------------------------- Members
    r.mark("members")
    r.click("nav.nav a[data-nav=members]", after=0.3); p.wait_for_selector("table.table"); r.wait(0.6)
    r.point("table.table tbody tr:nth-child(1) .why"); r.wait(2.0)
    r.click(".segmented a:nth-child(2)", after=0.3); p.wait_for_selector(".segmented a:nth-child(2)[aria-current]"); r.wait(2.0)
    r.click(".segmented a:nth-child(3)", after=0.3); p.wait_for_selector(".segmented a:nth-child(3)[aria-current]"); r.wait(2.0)

    # ---------------------------------------------------------------- Maria, a full case
    r.mark("maria_summary")
    r.click("nav.nav a[data-nav=case]", after=0.3); p.wait_for_selector(".answer"); r.wait(0.6)
    r.point(".answer-head"); r.wait(2.2)
    r.point(".window-lg .window-track"); r.wait(2.0)
    r.point(".gaps li:first-child h3"); r.wait(1.8)
    r.point(".steps li:first-child"); r.wait(1.6)

    r.mark("maria_documents")
    r.click(".subnav a:nth-child(2)", after=0.3); p.wait_for_selector(".doc-view")
    r.click(".doc-list a:nth-child(3)", after=0.3); p.wait_for_selector(".doc-img"); r.wait(2.0)
    r.click(".toggle a:nth-child(2)", after=0.3); p.wait_for_selector(".doc-text"); r.wait(1.8)

    r.mark("maria_letters")
    r.click(".subnav a:nth-child(3)", after=0.3); p.wait_for_selector(".letter-block")
    r.point(".prov-ai"); r.wait(2.2)
    r.point(".letter-block .sheet"); r.wait(2.0)
    r.scroll("#packet", secs=1.0)
    r.point("#packet .cite-doc"); r.wait(0.8)
    r.click("#packet .cite-doc", after=0.3); p.wait_for_selector(".doc-text .is-focus"); r.wait(2.0)

    r.mark("maria_evidence")
    r.click(".subnav a:nth-child(4)", after=0.3); p.wait_for_selector(".pathway"); r.wait(1.2)
    r.click("details.rest summary", after=1.2)

    r.mark("maria_agents")
    r.click(".subnav a:nth-child(5)", after=0.3); p.wait_for_selector(".stage-list"); r.wait(1.2)
    r.scroll("#verifier", secs=1.0); r.point(".log"); r.wait(1.6)

    # ---------------------------------------------------------------- the other two outcomes
    r.mark("devon_recover")
    r.scroll(".case-head", secs=0.5); r.point("[data-switch]")
    r.go("#/case/C47", ".answer")
    r.point(".outcome-tag"); r.wait(1.2)
    r.point(".window-lg .window-track"); r.wait(2.4)
    r.point(".steps"); r.wait(1.2)

    r.mark("kofi_transition")
    r.point("[data-switch]")
    r.go("#/case/C50", ".answer")
    r.point(".answer-head"); r.wait(1.8)
    r.scroll(".plan", secs=1.0)
    r.point(".options"); r.wait(1.6)
    r.point(".sheet-note"); r.wait(1.4)

    # ---------------------------------------------------------------- a new case, run live on the AI models
    r.mark("new_case")
    r.scroll(".case-head", secs=0.4); r.point("[data-switch]")
    r.go(f"#/case/{case_id}", ".empty")
    r.point(".empty h2"); r.wait(1.8)
    r.click(".run-settings summary", after=0.5)
    r.point("select[name=lang]"); r.wait(1.0)
    r.click(".run-box button[type=submit]", after=0.4)
    r.click(".subnav a:nth-child(5)", after=0.2)
    p.evaluate(LIVE_JS, "Live run on NVIDIA NIM, open-weight models")
    r.mark("run_live")
    deadline = time.monotonic() + 15 * 60
    while time.monotonic() < deadline:
        if p.evaluate("() => { const b = document.querySelector('.run-box button'); return !!b && !b.disabled; }"):
            break
        if r.has(".alert"):
            raise SystemExit("The live run stopped with an error; see the page. Nothing was cut.")
        p.evaluate("() => window.scrollTo({top: document.body.scrollHeight, behavior: 'smooth'})")
        r.wait(2.0)
    else:
        raise SystemExit("The live run took over 15 minutes.")
    p.evaluate(LIVE_DONE_JS)
    r.mark("run_done")
    r.wait(1.6)
    p.evaluate("() => document.getElementById('ck-live')?.remove()")

    r.mark("new_summary")
    r.click(".subnav a:nth-child(1)", after=0.3); p.wait_for_selector(".answer")
    r.point(".outcome-tag"); r.wait(1.2)
    r.point(".answer-head"); r.wait(2.4)
    r.point(".window-lg .window-track"); r.wait(1.8)
    r.point(".summary-grid"); r.wait(2.6)

    r.mark("new_evidence")
    r.click(".subnav a:nth-child(4)", after=0.3); p.wait_for_selector(".pathway")
    r.point(".pathway"); r.wait(2.0)
    if r.has("#int-h"):
        r.scroll("#int-h", secs=1.0)
        r.point("blockquote" if r.has("blockquote") else "#int-h"); r.wait(3.6)

    r.mark("new_letters")
    r.click(".subnav a:nth-child(3)", after=0.3); p.wait_for_selector(".letter-block")
    r.point(".prov"); r.wait(2.2)
    r.point(".letter-block .sheet"); r.wait(2.8)
    r.scroll("#packet", secs=1.0)
    if r.has("[data-consent]"):
        r.click("[data-consent]", after=0.5)
        r.click("[data-approve]", after=1.6)

    r.mark("new_agents")
    r.click(".subnav a:nth-child(5)", after=0.3); p.wait_for_selector(".stage-list")
    r.point(".stats-row"); r.wait(1.8)
    r.scroll(".stage-list li:nth-child(4)", block="center", secs=1.0); r.wait(1.6)
    r.scroll("#verifier", secs=1.0); r.wait(1.4)

    # ---------------------------------------------------------------- policy packs and safeguards
    r.mark("policies")
    r.click("nav.nav a[data-nav=policies]", after=0.3); p.wait_for_selector("[data-pack]")
    r.point(".lede"); r.wait(1.8)
    r.scroll("#pw-h", secs=0.8); r.point(".table-wrap"); r.wait(1.8)
    r.scroll("[data-pack]", block="center", secs=0.6); r.point("[data-pack]")
    p.select_option("[data-pack]", "employer_dependent_audit_demo"); p.wait_for_selector(".alert"); r.wait(2.6)
    p.select_option("[data-pack]", "masshealth_ce_2027"); p.wait_for_function("() => !document.querySelector('.alert')"); r.wait(0.6)

    r.mark("safeguards")
    r.click("nav.nav a[data-nav=safeguards]", after=0.3); p.wait_for_selector(".safeguards")
    r.point(".lede"); r.wait(1.8)
    r.point(".safeguards div:nth-child(1)"); r.wait(1.8)
    r.point(".safeguards div:nth-child(2)"); r.wait(1.8)
    r.point(".safeguards div:nth-child(7)"); r.wait(1.8)

    r.mark("closing")
    r.card("Coverage Keeper", ["Finds the members at risk, reads their papers, checks every rule and drafts the packet.",
                               "Every claim is cited. The agency decides. A person approves before anything is sent."], 7)
    r.mark("end")


def cut(raw, marks, target):
    """Trim the page-load frames, speed up the live run, upscale to 1080p; return the scene times in the cut."""
    t = {m["scene"]: m["raw"] for m in marks}
    start, a, b, end = t["title"], t["run_live"] + 0.6, t["run_done"], t["end"]
    rest = (a - start) + (end - b)
    run_len = max(8.0, min(30.0, target - rest))
    k = (b - a) / run_len
    out = OUT / "walkthrough.mp4"
    fc = (f"[0:v]trim=start={start}:end={a},setpts=PTS-STARTPTS[a];"
          f"[0:v]trim=start={a}:end={b},setpts=(PTS-STARTPTS)/{k:.4f}[b];"
          f"[0:v]trim=start={b}:end={end},setpts=PTS-STARTPTS[c];"
          "[a][b][c]concat=n=3:v=1:a=0,scale=1920:1080:flags=lanczos,fps=30,format=yuv420p[v]")
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(raw), "-filter_complex", fc,
                    "-map", "[v]", "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-movflags", "+faststart", str(out)], check=True)

    def final(x):
        if x <= a:
            return x - start
        if x <= b:
            return (a - start) + (x - a) / k
        return (a - start) + run_len + (x - b)

    scenes_out = [{"scene": m["scene"], "start": round(final(m["raw"]), 1)} for m in marks]
    meta = {"length_s": round(final(end), 1), "live_run_real_s": round(b - a, 1), "live_run_shown_s": round(run_len, 1),
            "speedup": round(k, 1), "scenes": scenes_out}
    (OUT / "timeline.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    return out, meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--case", required=True, help="id of a case that has not been run yet (it runs live on camera)")
    ap.add_argument("--target", type=float, default=TARGET)
    args = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    raw_dir = OUT / "raw"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="msedge", headless=True)
        ctx = browser.new_context(viewport=VIEW, record_video_dir=str(raw_dir), record_video_size=VIEW)
        page = ctx.new_page()
        rec = Recorder(page)
        page.goto(args.url + "/#/")
        page.wait_for_selector("h1:has-text('Today')")
        page.evaluate(CHROME_JS)
        page.mouse.move(VIEW["width"] / 2, VIEW["height"] / 2)
        scenes(rec, args.case)
        video = page.video.path()
        ctx.close()
        browser.close()
    raw = OUT / "raw_walkthrough.webm"
    Path(video).replace(raw)
    out, meta = cut(raw, rec.marks, args.target)
    print(f"\n{out}  {meta['length_s']} s (live run {meta['live_run_real_s']} s shown in {meta['live_run_shown_s']} s, "
          f"{meta['speedup']}x)\n{OUT / 'timeline.json'}")


if __name__ == "__main__":
    main()
