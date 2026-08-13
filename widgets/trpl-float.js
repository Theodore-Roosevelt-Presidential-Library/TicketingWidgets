/*!
 * TRPL Floating Sell-Out Banner — Theodore Roosevelt Presidential Library
 * Self-contained script for injection via Google Tag Manager (Custom HTML tag):
 *
 *   <script src="https://ticketing.labs.trlibrary.com/widgets/trpl-float.js" async></script>
 *
 * Behavior:
 *  - Docks a compact sell-out banner in the lower-left corner.
 *  - Shows only when it has something worth saying (medium+ risk, sold-out slots,
 *    or fully sold out). Quiet on good-availability days.
 *  - Dismissible; stays dismissed for the rest of the (Mountain Time) day across
 *    all pages via localStorage.
 *
 * Optional config — set BEFORE this script loads (e.g. in the same GTM tag):
 *   window.TRPL_FLOAT = {
 *     minRisk: "medium",           // "low" shows on any day | "medium" (default) | "high"
 *     ticketsUrl: "...",           // override Buy Tickets link
 *     availabilityUrl: "...",      // secondary "See today's availability" link
 *     dataUrl: "...availability.json",
 *     fontsCss: "https://use.typekit.net/XXXXXXX.css"  // load brand webfonts if the page doesn't
 *   };
 */
(function () {
  "use strict";
  if (window.__trplFloatLoaded) return;
  window.__trplFloatLoaded = true;

  var cfg = window.TRPL_FLOAT || {};
  var SCRIPT = document.currentScript;
  var BASE = SCRIPT && SCRIPT.src ? SCRIPT.src.replace(/widgets\/[^/]*$/, "") : "";
  var DATA_URL = cfg.dataUrl || BASE + "data/availability.json";
  var STORE_KEY = "trplFloatDismissed";
  var RANK = { low: 1, medium: 2, high: 3, sold_out: 4 };
  var MIN_RISK = RANK[cfg.minRisk] || 2;
  var STALE_MIN = 90;

  function esc(v) {
    return String(v == null ? "" : v).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function dismissedToday(todayIso) {
    try { return localStorage.getItem(STORE_KEY) === todayIso; } catch (e) { return false; }
  }
  function dismiss(todayIso) {
    try { localStorage.setItem(STORE_KEY, todayIso); } catch (e) { /* private mode */ }
  }

  var CSS = [
    "#trpl-float{position:fixed;left:1rem;bottom:1rem;z-index:99999;max-width:22.5rem;",
    "font-family:'ITC Clearface','itc-clearface','Clearface',Georgia,serif;color:#25282A;",
    "background:#FBF9F5;border:1px solid rgba(37,40,42,.2);border-left:6px solid #E7805D;",
    "border-radius:4px;box-shadow:0 6px 24px rgba(9,42,77,.25);padding:.95rem 1.05rem .9rem;",
    "line-height:1.45;opacity:0;transform:translateY(.75rem);transition:opacity .35s,transform .35s}",
    "#trpl-float.trpl-on{opacity:1;transform:none}",
    "#trpl-float strong{display:block;font-family:'Dharma Gothic E','dharma-gothic-e','Dharma Gothic','Arial Narrow',Impact,sans-serif;",
    "text-transform:uppercase;letter-spacing:.04em;font-size:1.2rem;line-height:1.15;color:#092A4D;",
    "margin:0 1.4rem .25rem 0}",
    "#trpl-float p{margin:0 0 .6rem;font-size:.88rem}",
    "#trpl-float a.trpl-float-btn{display:inline-block;background:#E7805D;color:#25282A;",
    "font-family:Frutiger,'Frutiger Next','frutiger-next','Helvetica Neue',Arial,sans-serif;",
    "font-weight:700;padding:10px 24px;border-radius:2px;text-decoration:none;font-size:.9rem}",
    "#trpl-float a.trpl-float-btn:hover{filter:brightness(1.07)}",
    "#trpl-float a.trpl-float-link{display:inline-block;margin-left:.9rem;font-family:Frutiger,'Frutiger Next','frutiger-next','Helvetica Neue',Arial,sans-serif;",
    "font-size:.8rem;color:#092A4D;text-decoration:underline;text-underline-offset:2px}",
    "#trpl-float a.trpl-float-link:hover{color:#1B4532}",
    "#trpl-float button.trpl-float-x{position:absolute;top:.35rem;right:.4rem;border:0;background:none;",
    "cursor:pointer;font-size:1.05rem;line-height:1;color:#25282A;opacity:.55;padding:.25rem}",
    "#trpl-float button.trpl-float-x:hover{opacity:1}",
    "@media (max-width:600px){#trpl-float{left:.6rem;right:.6rem;bottom:.6rem;max-width:none}}"
  ].join("");

  function message(today, days) {
    if (today.closed) return null;
    var risk = today.selloutRisk;
    if (risk === "sold_out") {
      var next = (days || []).filter(function (d) { return !d.closed && d.selloutRisk !== "sold_out"; })[0];
      return {
        risk: risk,
        head: "Today is sold out",
        body: "No walk-up tickets remain." + (next ? " Next availability: " + next.dayLabel + "." : ""),
        cta: "See All Dates"
      };
    }
    if (RANK[risk] < MIN_RISK && !today.soldOutSlots) return null;
    if (today.soldOutSlots > 0) {
      return {
        risk: risk,
        head: today.soldOutSlots + (today.soldOutSlots === 1 ? " time slot" : " time slots") + " sold out today",
        body: (today.firstAvailable ? "First available entry: " + today.firstAvailable + " MT. " : "") +
              (today.riskNote || "Reserve online before you drive."),
        cta: "Buy Tickets"
      };
    }
    return {
      risk: risk,
      head: "Today is selling fast",
      body: today.riskNote || "Buying online before you drive is recommended.",
      cta: "Buy Tickets"
    };
  }

  function show(data) {
    var today = data.days && data.days[0];
    if (!today || dismissedToday(data.today)) return;

    var mins = Math.round((Date.now() - Date.parse(data.generatedAt)) / 60000);
    if (isNaN(mins) || mins > STALE_MIN) return;  // stale data: stay quiet, don't mislead

    var msg = message(today, data.days);
    if (!msg) return;

    var style = document.createElement("style");
    style.textContent = CSS;
    document.head.appendChild(style);

    var fontsCss = cfg.fontsCss || window.TRPL_FONTS_CSS;
    if (fontsCss && !document.getElementById("trpl-tw-fonts")) {
      var link = document.createElement("link");
      link.id = "trpl-tw-fonts";
      link.rel = "stylesheet";
      link.href = fontsCss;
      document.head.appendChild(link);
    }

    var el = document.createElement("aside");
    el.id = "trpl-float";
    el.setAttribute("role", "status");
    el.setAttribute("aria-label", "Ticket availability");
    el.setAttribute("data-risk", msg.risk);
    el.innerHTML =
      '<button class="trpl-float-x" aria-label="Dismiss for today">&#10005;</button>' +
      "<strong>" + esc(msg.head) + "</strong>" +
      "<p>" + esc(msg.body) + "</p>" +
      '<a class="trpl-float-btn" href="' + esc(cfg.ticketsUrl || data.ticketsUrl || "https://www.trlibrary.com/tickets") +
      '">' + esc(msg.cta) + "</a>" +
      '<a class="trpl-float-link" href="' +
      esc(cfg.availabilityUrl || "https://www.trlibrary.com/tickets#available") +
      '">See today\u2019s availability</a>';
    document.body.appendChild(el);
    requestAnimationFrame(function () { requestAnimationFrame(function () { el.className = "trpl-on"; }); });

    el.querySelector(".trpl-float-x").addEventListener("click", function () {
      dismiss(data.today);
      el.style.opacity = "0";
      el.style.transform = "translateY(.75rem)";
      setTimeout(function () { el.remove(); }, 400);
    });
  }

  function boot() {
    fetch(DATA_URL + "?t=" + Math.floor(Date.now() / 60000), { cache: "no-store" })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(show)
      .catch(function (e) { if (window.console) console.warn("TRPL float banner:", e); });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
