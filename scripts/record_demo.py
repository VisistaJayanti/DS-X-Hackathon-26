"""Record a captioned walkthrough video of the demo (no audio).

Usage: start the app (python server.py), then: python scripts/record_demo.py
Output: demo_video/coverage_keeper_demo.webm  (plays in Chrome, Edge, VLC)
Requires: pip install playwright; python -m playwright install ffmpeg  (uses your installed Chrome)
"""
import shutil
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "demo_video"
URL = "http://127.0.0.1:8000/"
W, H = 1440, 900

CAPTION_JS = """(t) => {
  let el = document.getElementById('demo-caption');
  if (!el) {
    el = document.createElement('div'); el.id = 'demo-caption';
    el.style.cssText = 'position:fixed;left:50%;bottom:22px;transform:translateX(-50%);max-width:1180px;z-index:99999;' +
      'background:rgba(11,31,51,.93);color:#fff;font:600 19px/1.4 system-ui,Segoe UI,sans-serif;padding:14px 22px;border-radius:12px;' +
      'box-shadow:0 8px 30px rgba(0,0,0,.35);text-align:center;transition:opacity .3s';
    document.body.appendChild(el);
  }
  el.style.opacity = t ? 1 : 0; el.innerHTML = t || '';
}"""
TITLE_JS = """([title, sub]) => {
  const d = document.createElement('div'); d.id = 'demo-title';
  d.style.cssText = 'position:fixed;inset:0;z-index:100000;background:#0b1f33;color:#fff;display:flex;flex-direction:column;' +
    'align-items:center;justify-content:center;font-family:system-ui,Segoe UI,sans-serif;text-align:center;padding:40px';
  d.innerHTML = `<div style="font-size:52px;font-weight:800;margin-bottom:18px">${title}</div><div style="font-size:24px;color:#9fb3c8;max-width:1000px;line-height:1.5">${sub}</div>`;
  document.body.appendChild(d);
}"""


def main():
    OUT.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        ctx = browser.new_context(viewport={"width": W, "height": H}, record_video_dir=str(OUT),
                                  record_video_size={"width": W, "height": H})
        page = ctx.new_page()

        def cap(text, secs):
            page.evaluate(CAPTION_JS, text)
            time.sleep(secs)

        def scroll_to(selector, secs=1.2, block="start"):
            page.locator(selector).first.evaluate(f"e => e.scrollIntoView({{behavior: 'smooth', block: '{block}'}})")
            time.sleep(secs)

        def title(t, sub, secs):
            page.evaluate(TITLE_JS, [t, sub])
            time.sleep(secs)
            page.evaluate("() => document.getElementById('demo-title')?.remove()")

        def run_case(cid):
            page.evaluate(f"openCase('{cid}')")
            time.sleep(1.5)
            page.click("#run")
            page.wait_for_selector(".outcome-banner", timeout=60000)
            time.sleep(1.0)

        page.goto(URL)
        page.wait_for_selector("#roster tr")
        title("Coverage Keeper",
              "Retain eligible members. Recover those dropped by mistake. Transition those who no longer qualify, "
              "so nobody falls into a gap.<br><br><span style='font-size:18px'>All data is synthetic. Maria, Devon and Kofi are "
              "illustrative composites, not real people.</span>", 6)

        # ---- Plan view
        cap("In the 2023 Medicaid unwinding, 72–73% of people who lost coverage lost it over paperwork, not eligibility (KFF).", 5)
        cap("This is a health plan's view: members to RETAIN, members to RECOVER, members to TRANSITION.", 5)
        scroll_to("#roster", 1.5)
        cap("Every at-risk member gets a transparent risk score with plain reasons. Flags only decide who we help first.", 5)
        page.locator("tr.hl").first.evaluate("e => e.scrollIntoView({behavior:'smooth', block:'center'})")
        cap("Maria: her notice went out in English, she speaks Spanish, she moved, missed a notice — and plan data hints at a caregiver exemption.", 6)

        # ---- Maria (Retain)
        page.evaluate("openCase('C46')")
        time.sleep(1.5)
        cap("Maria's documents: the MassHealth letter, her handwritten Spanish caregiver statement, her mother's neurology letter.", 4)
        page.click("#doclist .doc-item:nth-child(2)")
        time.sleep(2.5)
        page.click("#run")
        cap("Eleven agents run in order. Each one's input and output can be inspected.", 7)
        page.wait_for_selector(".outcome-banner", timeout=60000)
        scroll_to(".outcome-banner", 1.5)
        cap("RETAIN: the agents find her likely pathway — caregiver of a person with a disability — with 18 days left.", 5)
        cap("And the gap a reminder app would never catch: her mother's doctor letter names the stroke but never says 'disability'.", 6)
        page.locator(".cite").first.click()
        time.sleep(2.0)
        cap("Every claim links to its proof. Here is the exact line in the doctor's letter.", 5)
        scroll_to("table.tbl", 1.5)
        cap("All 17 pathways are checked, each with its reason and the federal rule it is quoted from.", 5)
        scroll_to(".msg", 1.5)
        cap("Outreach in Spanish by text and phone. Every message gives the agency's own number and an opt-out.", 5)
        page.locator("h2:has-text('Member explanation')").first.evaluate("e => e.scrollIntoView({behavior:'smooth', block:'start'})")
        time.sleep(1.2)
        cap("Maria gets a plain-language explanation in Spanish: what she may qualify for, what's missing, the deadline.", 5)
        page.locator("h2:has-text('Response packet')").first.evaluate("e => e.scrollIntoView({behavior:'smooth', block:'start'})")
        time.sleep(1.2)
        cap("The packet is drafted and on hold until the missing letter arrives…", 4)
        page.locator("h2:has-text('Request for an updated clinician letter')").first.evaluate(
            "e => e.scrollIntoView({behavior:'smooth', block:'start'})")
        time.sleep(1.2)
        cap("…and the request to her mother's doctor is ready, asking for exactly the missing statement.", 5)
        page.locator("#confirm-send").evaluate("e => e.scrollIntoView({behavior:'smooth', block:'center'})")
        time.sleep(1.0)
        page.check("#confirm-send")
        cap("Nothing is sent until a human coordinator reviews it and confirms. The tool never decides eligibility.", 5)
        page.locator("h2:has-text('Verifier log')").first.evaluate("e => e.scrollIntoView({behavior:'smooth', block:'start'})")
        time.sleep(1.2)
        cap("The verifier checks every sentence against a document quote and a cited rule, and removes anything unsupported.", 5)

        # ---- Devon (Recover)
        page.click("nav button[data-tab='plan']")
        time.sleep(1.0)
        scroll_to("#recover-group", 1.5, "center")
        cap("RECOVER: members already dropped for paperwork, with the days left in their reconsideration window.", 5)
        run_case("C47")
        scroll_to(".outcome-banner", 1.5)
        cap("Devon was dropped 20 days ago because a pay stub never arrived. Federal rules allow 90 days: 70 days left.", 6)
        cap("The agents draft his reconsideration submission. He may get coverage back without a new application — never promised.", 6)

        # ---- Kofi (Transition)
        page.click("nav button[data-tab='plan']")
        time.sleep(1.0)
        scroll_to("#transition-group", 1.5, "center")
        cap("TRANSITION: members who may no longer qualify, with the date to enrol in next coverage without a gap.", 5)
        run_case("C50")
        scroll_to(".outcome-banner", 1.5)
        cap("Kofi's income rose. The tool never decides — it says the evidence suggests he may no longer qualify.", 5)
        page.locator("h2:has-text('Transition plan')").first.evaluate("e => e.scrollIntoView({behavior:'smooth', block:'start'})")
        time.sleep(1.2)
        cap("Options listed neutrally, the enrol-by date from the federal special-enrollment rule, and a warm hand-off to a navigator.", 7)

        # ---- Evaluation, packs, responsible AI
        page.click("nav button[data-tab='eval']")
        time.sleep(1.5)
        cap("Evaluated on 54 labelled synthetic cases with a held-out split: pathways, gaps, outcomes, deadlines.", 5)
        cap("Risk flags: 80% precision in the top 20, vs 15% deadline-first — on a roster calibrated to real CMS and Census data.", 6)
        page.click("nav button[data-tab='packs']")
        time.sleep(1.5)
        cap("Nothing is hard-coded to Massachusetts: every rule lives in a swappable policy pack, quoted from its source.", 6)
        page.select_option("#packsel", "employer_dependent_audit_demo")
        time.sleep(2.0)
        cap("Swap the pack — here an illustrative employer plan — and the same agents apply different rules. A new pack, not new code.", 6)
        page.select_option("#packsel", "masshealth_ce_2027")
        page.click("nav button[data-tab='rai']")
        time.sleep(1.5)
        cap("Guardrails: never decides eligibility, every claim cited, no false promises, neutral routing, synthetic data only.", 7)
        page.evaluate(CAPTION_JS, "")
        title("Coverage Keeper", "Insurers lose members to paperwork, not ineligibility.<br>Our agents don't just remind members — "
                                 "they finish the paperwork.", 5)

        video = page.video.path()
        ctx.close()
        browser.close()
    final = OUT / "coverage_keeper_demo.webm"
    shutil.move(video, final)
    print(f"saved {final} ({final.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    sys.exit(main())
