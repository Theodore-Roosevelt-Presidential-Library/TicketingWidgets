/*!
 * TRPL Ticketing Widgets — Theodore Roosevelt Presidential Library
 * Embeddable availability widgets fed by data/availability.json on GitHub Pages.
 *
 * Usage (drop anywhere on trlibrary.com):
 *   <script src="https://<pages-domain>/TicketingWidgets/widgets/trpl-tickets.js" defer></script>
 *   <div data-trpl-widget="alert"></div>
 *   <div data-trpl-widget="timeslots"></div>
 *   <div data-trpl-widget="planner"></div>
 *
 * Optional attributes on any container:
 *   data-url="...availability.json"   override data source
 *   data-tickets-url="..."            override Buy Tickets link
 *
 * Styling: fonts and text colors are inherited from the host page. Accent
 * colors can be overridden with CSS custom properties on any ancestor:
 *   --trpl-tw-accent, --trpl-tw-ok, --trpl-tw-warn, --trpl-tw-out, --trpl-tw-border
 */
(function () {
  "use strict";

  var SCRIPT = document.currentScript;
  var BASE = SCRIPT && SCRIPT.src ? SCRIPT.src.replace(/widgets\/[^/]*$/, "") : "";
  var DEFAULT_DATA_URL = BASE + "data/availability.json";
  var REFRESH_MS = 5 * 60 * 1000;
  var STALE_MIN = 90;

  var CSS = [
    ".trpl-tw{font-family:inherit;color:inherit;line-height:1.45;",
    "--_accent:var(--trpl-tw-accent,#8C3B2E);--_ok:var(--trpl-tw-ok,#3E6B4F);",
    "--_warn:var(--trpl-tw-warn,#B07C24);--_out:var(--trpl-tw-out,#8C3B2E);",
    "--_border:var(--trpl-tw-border,rgba(0,0,0,.14));}",
    ".trpl-tw *{box-sizing:border-box;margin:0;padding:0}",
    ".trpl-tw a.trpl-tw-btn{display:inline-block;background:var(--_accent);color:#fff;",
    "padding:.5em 1.1em;border-radius:4px;text-decoration:none;font-weight:600;font-size:.95em}",
    ".trpl-tw a.trpl-tw-btn:hover{filter:brightness(1.12)}",
    ".trpl-tw-meta{font-size:.78em;opacity:.65;margin-top:.6em}",
    /* alert banner */
    ".trpl-tw-alert{display:flex;flex-wrap:wrap;align-items:center;gap:.8em 1em;",
    "border:1px solid var(--_border);border-left:5px solid var(--_accent);",
    "border-radius:6px;padding:.9em 1.1em}",
    ".trpl-tw-alert[data-risk=low]{border-left-color:var(--_ok)}",
    ".trpl-tw-alert[data-risk=medium]{border-left-color:var(--_warn)}",
    ".trpl-tw-alert p{flex:1 1 16em;font-size:.98em}",
    ".trpl-tw-alert strong{display:block;margin-bottom:.15em}",
    /* timeslot grid */
    ".trpl-tw-slots h3{font-size:1.05em;margin-bottom:.5em}",
    ".trpl-tw-tabs{display:flex;gap:.4em;flex-wrap:wrap;margin-bottom:.8em}",
    ".trpl-tw-tabs button{border:1px solid var(--_border);background:transparent;color:inherit;",
    "border-radius:999px;padding:.3em .95em;cursor:pointer;font:inherit;font-size:.85em}",
    ".trpl-tw-tabs button[aria-selected=true]{background:var(--_accent);color:#fff;border-color:var(--_accent)}",
    ".trpl-tw-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(8.2em,1fr));gap:.5em;list-style:none}",
    ".trpl-tw-slot{border:1px solid var(--_border);border-radius:6px;padding:.55em .35em;text-align:center}",
    ".trpl-tw-slot b{display:block;font-size:.98em;font-weight:600}",
    ".trpl-tw-slot span{display:block;font-size:.72em;letter-spacing:.02em;margin-top:.2em}",
    ".trpl-tw-slot[data-s=available] span{color:var(--_ok)}",
    ".trpl-tw-slot[data-s=limited] span{color:var(--_warn)}",
    ".trpl-tw-slot[data-s=sold_out]{opacity:.55}",
    ".trpl-tw-slot[data-s=sold_out] b{text-decoration:line-through}",
    ".trpl-tw-slot[data-s=sold_out] span{color:var(--_out)}",
    ".trpl-tw-slot[data-s=past]{opacity:.35}",
    ".trpl-tw-cta{margin-top:.9em}",
    /* planner */
    ".trpl-tw-planner ul{list-style:none;display:grid;gap:.45em}",
    ".trpl-tw-day{display:flex;align-items:center;gap:.9em;border:1px solid var(--_border);",
    "border-radius:6px;padding:.55em .9em}",
    ".trpl-tw-day .d{flex:0 0 7em;font-weight:600;font-size:.92em}",
    ".trpl-tw-day .bar{flex:1;height:.55em;border-radius:999px;background:rgba(0,0,0,.08);overflow:hidden}",
    ".trpl-tw-day .bar i{display:block;height:100%;background:var(--_ok)}",
    ".trpl-tw-day[data-risk=medium] .bar i{background:var(--_warn)}",
    ".trpl-tw-day[data-risk=high] .bar i,.trpl-tw-day[data-risk=sold_out] .bar i{background:var(--_out)}",
    ".trpl-tw-day .lbl{flex:0 0 auto;font-size:.8em;min-width:9em;text-align:right}",
    ".trpl-tw-day[data-risk=high] .lbl,.trpl-tw-day[data-risk=sold_out] .lbl{color:var(--_out);font-weight:600}",
    ".trpl-tw-day[data-risk=medium] .lbl{color:var(--_warn)}",
    "@media (max-width:480px){.trpl-tw-day .lbl{min-width:6.5em}}"
  ].join("");

  function injectStyles() {
    if (document.getElementById("trpl-tw-styles")) return;
    var s = document.createElement("style");
    s.id = "trpl-tw-styles";
    s.textContent = CSS;
    document.head.appendChild(s);
  }

  function esc(v) {
    return String(v == null ? "" : v).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function minutesSince(iso) {
    var t = Date.parse(iso);
    return isNaN(t) ? null : Math.round((Date.now() - t) / 60000);
  }

  function slotWord(s) {
    return { available: "Available", limited: "Few left", sold_out: "Sold out", past: "Ended" }[s] || "";
  }

  var cache = {};
  function getData(url) {
    if (!cache[url]) {
      cache[url] = fetch(url + (url.indexOf("?") < 0 ? "?" : "&") + "t=" + Math.floor(Date.now() / 60000), {
        cache: "no-store"
      }).then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      });
      cache[url].catch(function () { delete cache[url]; });
    }
    return cache[url];
  }

  /* ------------------------------------------------ renderers */

  function renderAlert(el, data, ticketsUrl) {
    var today = data.days && data.days[0];
    if (!today) return;
    var mins = minutesSince(data.generatedAt);
    var stale = mins != null && mins > STALE_MIN;
    var risk = today.closed ? "none" : today.selloutRisk;
    var head, body;

    if (today.closed) {
      var nextOpen = (data.days || []).filter(function (d) { return !d.closed; })[0];
      head = "The Library is closed today.";
      body = nextOpen ? "Next open: " + nextOpen.dayLabel + ". Reserve tickets in advance." : "";
    } else if (risk === "sold_out") {
      head = "Today is sold out.";
      body = "No walk-up tickets are available. Check the next few days and reserve online.";
    } else if (today.soldOutSlots > 0) {
      head = today.soldOutSlots + (today.soldOutSlots === 1 ? " time slot has" : " time slots have") + " already sold out today.";
      body = (today.firstAvailable ? "First available entry: " + today.firstAvailable + " MT. " : "") + (today.riskNote || "");
    } else if (risk === "high" || risk === "medium") {
      head = "Today is selling fast.";
      body = today.riskNote || "Buying online before you drive is recommended.";
    } else {
      head = "Tickets are available today.";
      body = "Reserving online guarantees your entry time.";
    }
    if (stale) body += " (Availability shown may be out of date.)";

    el.innerHTML =
      '<div class="trpl-tw"><div class="trpl-tw-alert" role="status" data-risk="' + esc(risk) + '">' +
      "<p><strong>" + esc(head) + "</strong>" + esc(body) + "</p>" +
      (risk !== "sold_out" && !today.closed
        ? '<a class="trpl-tw-btn" href="' + esc(ticketsUrl) + '">Buy Tickets</a>'
        : '<a class="trpl-tw-btn" href="' + esc(ticketsUrl) + '">See All Dates</a>') +
      "</div></div>";
  }

  function renderTimeslots(el, data, ticketsUrl) {
    var days = (data.days || []).slice(0, 3);
    if (!days.length) return;
    var state = { idx: 0 };

    function draw() {
      var day = days[state.idx];
      var tabs = days.map(function (d, i) {
        return '<button role="tab" aria-selected="' + (i === state.idx) + '" data-i="' + i + '">' +
          esc(d.dayLabel) + "</button>";
      }).join("");
      var body;
      if (day.closed) {
        body = "<p>The Library is closed this day.</p>";
      } else {
        body = '<ul class="trpl-tw-grid">' + day.slots.map(function (s) {
          return '<li class="trpl-tw-slot" data-s="' + esc(s.status) + '"><b>' + esc(s.label) + "</b><span>" +
            esc(s.status === "limited" && s.remaining <= 25 ? s.remaining + " left" : slotWord(s.status)) +
            "</span></li>";
        }).join("") + "</ul>";
        if (day.firstAvailable && day.soldOutSlots > 0) {
          body = "<p style=\"margin-bottom:.6em;font-size:.9em\">First available entry: <strong>" +
            esc(day.firstAvailable) + " MT</strong></p>" + body;
        }
      }
      var mins = minutesSince(data.generatedAt);
      el.innerHTML =
        '<div class="trpl-tw trpl-tw-slots">' +
        "<h3>Timed-Entry Availability</h3>" +
        '<div class="trpl-tw-tabs" role="tablist">' + tabs + "</div>" + body +
        '<div class="trpl-tw-cta"><a class="trpl-tw-btn" href="' + esc(ticketsUrl) + '">Reserve Tickets</a></div>' +
        '<p class="trpl-tw-meta">Times shown in Mountain Time.' +
        (mins != null ? " Updated " + (mins <= 1 ? "just now" : mins + " min ago") + "." : "") + "</p></div>";
      el.querySelectorAll(".trpl-tw-tabs button").forEach(function (b) {
        b.addEventListener("click", function () { state.idx = +b.getAttribute("data-i"); draw(); });
      });
    }
    draw();
  }

  function renderPlanner(el, data, ticketsUrl) {
    var days = data.days || [];
    if (!days.length) return;
    var rows = days.map(function (d) {
      var pct = d.closed ? 0 : Math.min(100, d.pctSold);
      var lbl = d.closed ? "Closed" :
        d.selloutRisk === "sold_out" ? "Sold out" :
        d.selloutRisk === "high" ? "Likely to sell out" :
        d.selloutRisk === "medium" ? "Filling up" : "Good availability";
      return '<li class="trpl-tw-day" data-risk="' + esc(d.closed ? "closed" : d.selloutRisk) + '">' +
        '<span class="d">' + esc(d.dayLabel) + "</span>" +
        '<span class="bar" aria-hidden="true"><i style="width:' + pct + '%"></i></span>' +
        '<span class="lbl">' + esc(lbl) + "</span></li>";
    }).join("");
    el.innerHTML =
      '<div class="trpl-tw trpl-tw-planner"><h3 style="font-size:1.05em;margin-bottom:.6em">Best Days to Visit</h3>' +
      "<ul>" + rows + "</ul>" +
      '<div class="trpl-tw-cta" style="margin-top:.9em"><a class="trpl-tw-btn" href="' + esc(ticketsUrl) +
      '">Reserve Your Day</a></div></div>';
  }

  /* ------------------------------------------------ bootstrap */

  var RENDERERS = { alert: renderAlert, timeslots: renderTimeslots, planner: renderPlanner };

  function initAll() {
    injectStyles();
    var nodes = document.querySelectorAll("[data-trpl-widget]");
    nodes.forEach(function (el) {
      var kind = el.getAttribute("data-trpl-widget");
      var render = RENDERERS[kind];
      if (!render) return;
      var url = el.getAttribute("data-url") || DEFAULT_DATA_URL;
      function refresh() {
        getData(url).then(function (data) {
          var ticketsUrl = el.getAttribute("data-tickets-url") || data.ticketsUrl ||
            "https://www.trlibrary.com/tickets";
          render(el, data, ticketsUrl);
        }).catch(function (err) {
          /* Fail quietly: never break the host page. */
          if (window.console) console.warn("TRPL widget (" + kind + "):", err);
        });
      }
      refresh();
      setInterval(function () { cache = {}; refresh(); }, REFRESH_MS);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initAll);
  } else {
    initAll();
  }
})();
