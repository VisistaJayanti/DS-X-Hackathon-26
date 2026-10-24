// Secure document viewing (feature 1).
//
// Honest limits: a web page cannot fully block screenshots. The phone's operating system takes them, and
// anyone can photograph the screen. These are deterrents that make casual capture harder and traceable:
//   * on touch screens, documents stay blurred until the person presses and holds on them
//   * documents blur whenever the tab or app loses focus (app switcher, screenshot shortcuts on desktop)
//   * a watermark with the viewer's name and the time sits over every document, so leaked images are traceable
//   * no right-click, long-press menu, text selection, copy, drag or printing inside secure areas
const Secure = (() => {
  const SEL = ".secure-doc";
  const touch = window.matchMedia("(pointer: coarse)").matches;
  let viewer = "Coverage Keeper user";

  function watermarkText() {
    const t = new Date().toISOString().slice(0, 16).replace("T", " ");
    return `${viewer} · ${t} · CONFIDENTIAL`;
  }

  // The watermark is a repeating SVG tile in the background, so it covers the whole document as it scrolls
  // and shows up in any screenshot or photo of the screen.
  function stamp(el) {
    const text = watermarkText().replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="560" height="180"><text x="20" y="130" transform="rotate(-14 280 90)" ` +
      `font-family="system-ui,sans-serif" font-size="13" font-weight="600" fill="rgba(185,28,28,0.16)">${text}</text></svg>`;
    el.style.backgroundImage = `url("data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}")`;
  }

  function protect(el) {
    if (!el || el.dataset.secured) { if (el) stamp(el); return; }
    el.dataset.secured = "1";
    el.classList.add("secure-doc");
    if (touch) el.classList.add("hold-to-view", "veiled");
    stamp(el);
    const block = (e) => e.preventDefault();
    ["contextmenu", "copy", "cut", "dragstart", "selectstart"].forEach((ev) => el.addEventListener(ev, block));
    if (touch) {
      // Press and hold to reveal; anything that ends the press hides it again.
      const show = () => el.classList.remove("veiled");
      const hide = () => el.classList.add("veiled");
      el.addEventListener("pointerdown", show);
      ["pointerup", "pointercancel", "pointerleave"].forEach((ev) => el.addEventListener(ev, hide));
      el.addEventListener("touchstart", show, { passive: true });
      el.addEventListener("touchend", hide);
    }
  }

  function veilAll(on) { document.querySelectorAll(SEL).forEach((el) => el.classList.toggle("veiled", on)); }

  // Blur when the page is hidden or loses focus (switching apps, opening the screenshot tool, sharing screen).
  document.addEventListener("visibilitychange", () => veilAll(document.hidden));
  window.addEventListener("blur", () => veilAll(true));
  window.addEventListener("focus", () => { if (!touch) veilAll(false); });

  // Keyboard shortcuts for print / save / copy / screenshot (desktop).
  window.addEventListener("keydown", (e) => {
    const k = e.key.toLowerCase();
    if ((e.ctrlKey || e.metaKey) && ["p", "s", "c"].includes(k) && document.querySelector(SEL)) {
      e.preventDefault();
    }
    if (k === "printscreen" || (e.metaKey && e.shiftKey && ["3", "4", "5", "s"].includes(k))) {
      veilAll(true);
      try { navigator.clipboard?.writeText("Screenshots of documents are not allowed."); } catch (_) {}
      setTimeout(() => { if (!touch) veilAll(false); }, 1500);
    }
  });
  window.addEventListener("keyup", (e) => {
    if (e.key === "PrintScreen") { try { navigator.clipboard?.writeText(""); } catch (_) {} }
  });
  window.addEventListener("beforeprint", () => veilAll(true));
  window.addEventListener("afterprint", () => { if (!touch) veilAll(false); });

  // Re-stamp the watermark time every minute.
  setInterval(() => document.querySelectorAll(SEL).forEach(stamp), 60000);

  return { protect, setViewer: (name) => { viewer = name || viewer; document.querySelectorAll(SEL).forEach(stamp); }, touch };
})();
