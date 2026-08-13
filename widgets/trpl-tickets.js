/*!
 * TRPL Ticketing Widgets — Theodore Roosevelt Presidential Library
 * Embeddable availability widgets fed by data/availability.json (+ analytics.json)
 * published to GitHub Pages by the update-availability Action.
 *
 * Usage (drop anywhere on trlibrary.com):
 *   <script src="https://ticketing.labs.trlibrary.com/widgets/trpl-tickets.js" defer></script>
 *   <div data-trpl-widget="alert"></div>
 *   <div data-trpl-widget="timeslots"></div>
 *   <div data-trpl-widget="planner"></div>
 *   <div data-trpl-widget="datecheck"></div>
 *   <div data-trpl-widget="outlook"></div>   (month narrative; data-hide-heading available)
 *   <div data-trpl-widget="calendar"></div>  (year heatmap; data-hide-heading/-legend/-cta)
 *
 * Optional attributes on any container:
 *   data-url="...availability.json"   override data source
 *   data-tickets-url="..."            override Buy Tickets link
 *   data-hide-cta                     hide the Buy Tickets button (alert, timeslots, planner)
 *
 * Styling matches the TRPL Brand Identity System as implemented on trlibrary.com:
 *   Headlines: Dharma Gothic E (all caps, Night Sky) · Body: Clearface ·
 *   Section titles/buttons: Frutiger (buttons: bold, sentence case, Deep Orange
 *   #E7805D bg, Dark Gray #25282A text, 2px radius — same as the site's CTAs)
 *   Guide colors only: Bright Forest #8FC895, Sunset Orange #FC924E,
 *   Deep Orange #E7805D, Night Sky #092A4D, Sand #D1CCBD, Dark Gray #25282A
 * trlibrary.com self-hosts the fonts as "Clearface", "Dharma Gothic E",
 * "Frutiger" — all in the stacks below, so real fonts render automatically.
 * Overridable via CSS vars:
 *   --trpl-tw-display, --trpl-tw-body, --trpl-tw-caption, --trpl-tw-cta,
 *   --trpl-tw-forest, --trpl-tw-night, --trpl-tw-sand, --trpl-tw-warn, --trpl-tw-border
 */
(function () {
  "use strict";

  var SCRIPT = document.currentScript;
  var BASE = SCRIPT && SCRIPT.src ? SCRIPT.src.replace(/widgets\/[^/]*$/, "") : "";
  var DEFAULT_DATA_URL = BASE + "data/availability.json";
  var ANALYTICS_URL = BASE + "data/analytics.json";
  var REFRESH_MS = 5 * 60 * 1000;
  var STALE_MIN = 90;
  var FORECAST_CAVEAT_DAYS = 45;

  var CSS = [
    ".trpl-tw{color:var(--trpl-tw-ink,#25282A);line-height:1.5;",
    /* Both spellings covered: self-hosted/theme names and Adobe Fonts kit names */
    "font-family:var(--trpl-tw-body,'ITC Clearface','itc-clearface','Clearface',Georgia,'Times New Roman',serif);",
    "--_display:var(--trpl-tw-display,'Dharma Gothic E','dharma-gothic-e','Dharma Gothic','Arial Narrow',Impact,sans-serif);",
    "--_caption:var(--trpl-tw-caption,'Frutiger Next','frutiger-next',Frutiger,'Helvetica Neue',Arial,sans-serif);",
    "--_cta:var(--trpl-tw-cta,#E7805D);--_forest:var(--trpl-tw-forest,#1B4532);",
    "--_night:var(--trpl-tw-night,#092A4D);--_bright:var(--trpl-tw-bright,#8FC895);",
    "--_sand:var(--trpl-tw-sand,#D1CCBD);--_ink:var(--trpl-tw-ink,#25282A);",
    "--_warn:var(--trpl-tw-warn,#E7805D);--_border:var(--trpl-tw-border,rgba(37,40,42,.18));}",
    ".trpl-tw *{box-sizing:border-box;margin:0;padding:0}",
    ".trpl-tw h3{font-family:var(--_caption);text-transform:uppercase;letter-spacing:.05em;",
    "font-weight:700;color:var(--_ink);font-size:1em;line-height:1.2;margin-bottom:.6em}",
    ".trpl-tw a.trpl-tw-btn{display:inline-block;background:var(--_cta);color:var(--_ink);",
    "font-family:var(--_caption);font-weight:700;",
    "padding:10px 24px;border-radius:2px;text-decoration:none;font-size:1em;line-height:1.2}",
    ".trpl-tw a.trpl-tw-btn:hover{filter:brightness(1.07)}",
    ".trpl-tw-meta{font-family:var(--_caption);font-size:.74em;opacity:.7;margin-top:.7em}",
    /* alert banner */
    ".trpl-tw-alert{display:flex;flex-wrap:wrap;align-items:center;gap:.8em 1.1em;",
    "background:rgba(209,204,189,.22);border:1px solid var(--_border);",
    "border-left:6px solid var(--_cta);border-radius:4px;padding:1em 1.2em}",
    ".trpl-tw-alert[data-risk=low]{border-left-color:var(--_bright)}",
    ".trpl-tw-alert[data-risk=none]{border-left-color:var(--_night)}",
    ".trpl-tw-alert p{flex:1 1 16em;font-size:1em}",
    ".trpl-tw-alert strong{display:block;font-family:var(--_display);text-transform:uppercase;",
    "letter-spacing:.04em;font-size:1.25em;line-height:1.15;color:var(--_night);margin-bottom:.2em}",
    /* tabs + slot grid */
    ".trpl-tw-tabs{display:flex;gap:.4em;flex-wrap:wrap;margin-bottom:.9em}",
    ".trpl-tw-tabs button{border:1px solid var(--_border);background:transparent;color:var(--_ink);",
    "border-radius:999px;padding:.32em 1em .28em;cursor:pointer;font-family:var(--_caption);font-size:.82em}",
    ".trpl-tw-tabs button[aria-selected=true]{background:var(--_night);color:#fff;border-color:var(--_night)}",
    ".trpl-tw-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(8.2em,1fr));gap:.5em;list-style:none}",
    ".trpl-tw-slot{border:1px solid var(--_border);border-radius:4px;padding:.6em .35em .5em;",
    "text-align:center;background:#fff}",
    ".trpl-tw-slot b{display:block;font-family:var(--_display);font-weight:700;font-size:1.25em;",
    "letter-spacing:.03em;color:var(--_night)}",
    ".trpl-tw-slot span{display:block;font-family:var(--_caption);font-size:.7em;",
    "letter-spacing:.05em;text-transform:uppercase;margin-top:.25em}",
    ".trpl-tw-slot[data-s=available]{border-color:var(--_forest)}",
    ".trpl-tw-slot[data-s=available] span{color:var(--_forest)}",
    ".trpl-tw-slot[data-s=limited]{border-color:var(--_warn)}",
    ".trpl-tw-slot[data-s=limited] span{color:var(--_ink);font-weight:700}",
    ".trpl-tw-slot[data-s=sold_out]{background:rgba(209,204,189,.35);opacity:.75}",
    ".trpl-tw-slot[data-s=sold_out] b{text-decoration:line-through;color:var(--_ink);opacity:.6}",
    ".trpl-tw-slot[data-s=sold_out] span{color:var(--_ink);opacity:.8}",
    ".trpl-tw-slot[data-s=past]{opacity:.35}",
    ".trpl-tw-cta{margin-top:1em}",
    ".trpl-tw-firstnote{font-size:.92em;margin-bottom:.7em}",
    ".trpl-tw-firstnote strong{color:var(--_forest)}",
    /* planner */
    ".trpl-tw-planner ul{list-style:none;display:grid;gap:.45em}",
    ".trpl-tw-day{display:flex;align-items:center;gap:.9em;border:1px solid var(--_border);",
    "border-radius:4px;padding:.55em .95em;background:#fff}",
    ".trpl-tw-day .d{flex:0 0 7.5em;font-family:var(--_display);text-transform:uppercase;",
    "letter-spacing:.04em;font-weight:700;font-size:1.05em;color:var(--_night)}",
    ".trpl-tw-day .bar{flex:1;height:.55em;border-radius:999px;background:rgba(209,204,189,.5);overflow:hidden}",
    ".trpl-tw-day .bar i{display:block;height:100%;background:var(--_bright)}",
    ".trpl-tw-day[data-risk=medium] .bar i{background:var(--trpl-tw-medium,#FC924E)}",
    ".trpl-tw-day[data-risk=high] .bar i{background:var(--_warn)}",
    ".trpl-tw-day[data-risk=sold_out] .bar i{background:var(--_night)}",
    ".trpl-tw-day .lbl{flex:0 0 auto;font-family:var(--_caption);font-size:.78em;min-width:9.5em;text-align:right}",
    ".trpl-tw-day[data-risk=high] .lbl,.trpl-tw-day[data-risk=sold_out] .lbl{color:var(--_ink);font-weight:700}",
    /* date check */
    ".trpl-tw-datecheck .trpl-tw-pick{display:flex;gap:.7em;align-items:center;flex-wrap:wrap;margin-bottom:1em}",
    ".trpl-tw-pick label{font-family:var(--_caption);font-size:.85em}",
    ".trpl-tw-pick input[type=date]{font-family:var(--_caption);font-size:1em;padding:.35em .5em;",
    "border:1px solid var(--_border);border-radius:3px;background:#fff;color:var(--_ink)}",
    ".trpl-tw-forecast{border:1px solid var(--_border);border-left:6px solid var(--_night);",
    "border-radius:4px;background:rgba(209,204,189,.22);padding:1em 1.2em}",
    ".trpl-tw-forecast[data-risk=high]{border-left-color:var(--_warn)}",
    ".trpl-tw-forecast[data-risk=low]{border-left-color:var(--_bright)}",
    ".trpl-tw-forecast h4{font-family:var(--_display);text-transform:uppercase;letter-spacing:.04em;",
    "font-size:1.3em;line-height:1.15;color:var(--_night);margin-bottom:.35em}",
    ".trpl-tw-forecast p{font-size:.95em;margin-bottom:.4em}",
    ".trpl-tw-fslots{list-style:none;display:grid;grid-template-columns:repeat(auto-fill,minmax(8.2em,1fr));",
    "gap:.4em;margin:.7em 0 .2em}",
    ".trpl-tw-fslots li{border:1px solid var(--_border);border-radius:4px;background:#fff;",
    "padding:.45em .3em;text-align:center}",
    ".trpl-tw-fslots b{display:block;font-family:var(--_display);font-size:1.1em;letter-spacing:.03em;color:var(--_night)}",
    ".trpl-tw-fslots span{display:block;font-family:var(--_caption);font-size:.66em;",
    "text-transform:uppercase;letter-spacing:.04em;margin-top:.2em}",
    ".trpl-tw-fslots li[data-f=high] span{color:var(--_ink);font-weight:700}",
    ".trpl-tw-fslots li[data-f=med] span{color:var(--_ink)}",
    ".trpl-tw-fslots li[data-f=low] span{color:var(--_forest)}",
    /* year calendar heatmap */
    ".trpl-tw-cal-months{display:grid;grid-template-columns:repeat(auto-fill,minmax(13.5em,1fr));gap:1em}",
    ".trpl-tw-cal-month{background:#fff;border:1px solid var(--_border);border-radius:6px;padding:.65em .75em .75em}",
    ".trpl-tw-cal-month h4{font-family:var(--_caption);font-size:.78em;text-transform:uppercase;",
    "letter-spacing:.05em;color:var(--_night);margin-bottom:.5em}",
    ".trpl-tw-cal-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:3px}",
    ".trpl-tw-cal-grid .dw{font-family:var(--_caption);font-size:.55em;text-align:center;opacity:.5;text-transform:uppercase}",
    ".trpl-tw-cal-grid .dd{aspect-ratio:1;border-radius:3px;background:#F0EDE6}",
    ".trpl-tw-cal-grid .dd.today{outline:2px solid var(--_night);outline-offset:1px}",
    ".trpl-tw-cal-grid .dd.ghost{background:transparent!important;border:2px dashed rgba(37,40,42,.35)}",
    ".trpl-tw-cal-years{display:flex;gap:.4em;margin:.2em 0 1em}",
    ".trpl-tw-cal-years button{border:1px solid var(--_border);background:transparent;color:var(--_ink);",
    "border-radius:999px;padding:.3em 1em;cursor:pointer;font-family:var(--_caption);font-size:.82em}",
    ".trpl-tw-cal-years button[aria-pressed=true]{background:var(--_night);color:#fff;border-color:var(--_night)}",
    ".trpl-tw-cal-legend{display:flex;flex-wrap:wrap;gap:.9em;margin:.2em 0 1em;font-family:var(--_caption);font-size:.72em}",
    ".trpl-tw-cal-legend i{display:inline-block;width:1em;height:1em;border-radius:3px;vertical-align:-2px;margin-right:.3em}",
    "@media (max-width:480px){.trpl-tw-day .lbl{min-width:6.5em}}"
  ].join("");

  function injectStyles() {
    if (document.getElementById("trpl-tw-styles")) return;
    var s = document.createElement("style");
    s.id = "trpl-tw-styles";
    s.textContent = CSS;
    document.head.appendChild(s);
    // Optionally load the real brand webfonts (e.g. an Adobe Fonts kit CSS URL)
    // when the host page doesn't already: set data-fonts-css on the script tag
    // or window.TRPL_FONTS_CSS before it loads.
    var fontsCss = (SCRIPT && SCRIPT.getAttribute("data-fonts-css")) || window.TRPL_FONTS_CSS;
    if (fontsCss && !document.getElementById("trpl-tw-fonts")) {
      var l = document.createElement("link");
      l.id = "trpl-tw-fonts";
      l.rel = "stylesheet";
      l.href = fontsCss;
      document.head.appendChild(l);
    }
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

  function slotLabel(hhmm) {
    var h = +hhmm.slice(0, 2), m = hhmm.slice(3, 5);
    var suf = h < 12 ? "AM" : "PM";
    var h12 = h % 12 || 12;
    return h12 + ":" + m + " " + suf;
  }

  var DOW = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
  function dowOf(iso) {
    return DOW[new Date(iso + "T12:00:00").getDay()];
  }
  function prettyDate(iso) {
    return new Date(iso + "T12:00:00").toLocaleDateString("en-US",
      { weekday: "long", month: "long", day: "numeric" });
  }

  var cache = {};
  function getJson(url) {
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

  /* ------------------------------------------------ shared pieces */

  function slotGridHtml(day) {
    var html = "";
    if (day.firstAvailable && day.soldOutSlots > 0) {
      html += '<p class="trpl-tw-firstnote">First available entry: <strong>' +
        esc(day.firstAvailable) + " MT</strong></p>";
    }
    html += '<ul class="trpl-tw-grid">' + day.slots.map(function (s) {
      return '<li class="trpl-tw-slot" data-s="' + esc(s.status) + '"><b>' + esc(s.label) + "</b><span>" +
        esc(s.status === "limited" && s.remaining <= 25 ? s.remaining + " left" : slotWord(s.status)) +
        "</span></li>";
    }).join("") + "</ul>";
    return html;
  }

  /* ------------------------------------------------ renderers */

  function ticketsLeft(today) {
    var n = 0;
    (today.slots || []).forEach(function (s) {
      if (s.status === "available" || s.status === "limited") n += s.remaining;
    });
    return n;
  }
  function leftHeadline(n) {
    if (n <= 10) return "Only " + n + (n === 1 ? " ticket" : " tickets") + " left today";
    var r = n < 50 ? Math.round(n / 5) * 5 : Math.round(n / 10) * 10;
    return "About " + r + " tickets left today";
  }


  function renderAlert(el, data, ticketsUrl) {
    var today = data.days && data.days[0];
    if (!today) return;
    var mins = minutesSince(data.generatedAt);
    var stale = mins != null && mins > STALE_MIN;
    var risk = today.closed ? "none" : today.selloutRisk;
    var head, body;

    if (today.closed) {
      var nextOpen = (data.days || []).filter(function (d) { return !d.closed; })[0];
      head = "The Library is closed today";
      body = nextOpen ? "Next open: " + nextOpen.dayLabel + ". Reserve tickets in advance." : "";
    } else if (risk === "sold_out") {
      head = "Today is sold out";
      body = "No walk-up tickets are available. Check the next few days and reserve online.";
    } else if (today.soldOutSlots > 0 || risk === "high") {
      var left = ticketsLeft(today);
      head = left > 0 ? leftHeadline(left) : "Today is selling fast";
      body = (today.firstAvailable ? "First available entry: " + today.firstAvailable + " MT. " : "") + (today.riskNote || "");
    } else if (risk === "high" || risk === "medium") {
      head = "Today is selling fast";
      body = today.riskNote || "Buying online before you drive is recommended.";
    } else {
      head = "Tickets are available today";
      body = "Reserving online guarantees your entry time.";
    }
    if (stale) body += " (Availability shown may be out of date.)";

    var cta = el.hasAttribute("data-hide-cta") ? "" :
      '<a class="trpl-tw-btn" href="' + esc(ticketsUrl) + '">' +
      (risk === "sold_out" || today.closed ? "See All Dates" : "Buy Tickets") + "</a>";
    el.innerHTML =
      '<div class="trpl-tw"><div class="trpl-tw-alert" role="status" data-risk="' + esc(risk) + '">' +
      "<p><strong>" + esc(head) + "</strong>" + esc(body) + "</p>" + cta +
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
      var body = day.closed ? "<p>The Library is closed this day.</p>" : slotGridHtml(day);
      var mins = minutesSince(data.generatedAt);
      var cta = el.hasAttribute("data-hide-cta") ? "" :
        '<div class="trpl-tw-cta"><a class="trpl-tw-btn" href="' + esc(ticketsUrl) + '">Reserve Tickets</a></div>';
      el.innerHTML =
        '<div class="trpl-tw trpl-tw-slots">' +
        "<h3>Timed-Entry Availability</h3>" +
        '<div class="trpl-tw-tabs" role="tablist">' + tabs + "</div>" + body + cta +
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
    var cta = el.hasAttribute("data-hide-cta") ? "" :
      '<div class="trpl-tw-cta"><a class="trpl-tw-btn" href="' + esc(ticketsUrl) + '">Reserve Your Day</a></div>';
    el.innerHTML =
      '<div class="trpl-tw trpl-tw-planner"><h3>Best Days to Visit</h3>' +
      "<ul>" + rows + "</ul>" + cta + "</div>";
  }

  /* ---------------- month outlook: server-generated narrative text */

  function renderOutlook(el, data, ticketsUrl) {
    getJson(el.getAttribute("data-analytics-url") || ANALYTICS_URL).then(function (analytics) {
      var o = analytics && analytics.monthOutlook;
      if (!o || !o.text) return;
      var cta = el.hasAttribute("data-hide-cta") ? "" :
        '<div class="trpl-tw-cta"><a class="trpl-tw-btn" href="' + esc(ticketsUrl) + '">Reserve Tickets</a></div>';
      el.innerHTML =
        '<div class="trpl-tw trpl-tw-outlook">' +
        (el.hasAttribute("data-hide-heading") ? "" : "<h3>" + esc(o.heading) + "</h3>") +
        "<p>" + esc(o.text) + "</p>" + cta +
        '<p class="trpl-tw-meta">Based on recent ticket sales at the Library.</p></div>';
    }).catch(function (err) {
      if (window.console) console.warn("TRPL widget (outlook):", err);
    });
  }

  /* ---------------- date check: live window if we have it, forecast beyond */

  function forecastHtml(dateIso, analytics, ticketsUrl) {
    var dow = dowOf(dateIso);
    var a = analytics && analytics.byDayOfWeek && analytics.byDayOfWeek[dow];
    if (!a || !a.daysObserved) {
      return '<div class="trpl-tw-forecast"><h4>' + esc(prettyDate(dateIso)) + "</h4>" +
        "<p>Ticket sales for this date open closer to the day. Reserving in advance is the surest way in.</p>" +
        '<div class="trpl-tw-cta"><a class="trpl-tw-btn" href="' + esc(ticketsUrl) + '">Reserve Tickets</a></div></div>';
    }

    var n = a.daysObserved;
    var median = a.medianFinalPctSold || 0;
    var selloutCount = a.fullSelloutCount || 0;
    var firstEnd = a.typicalFirstAvailableAtEndOfDay;
    var risk = (selloutCount / n >= 0.5 || median >= 90) ? "high" : median >= 65 ? "medium" : "low";

    var head, lead;
    if (risk === "high") {
      head = dow + "s have been selling out";
      lead = "Recent " + dow + "s ended " + median + "% full" +
        (selloutCount ? ", and " + selloutCount + " of the last " + n + " sold out completely" : "") + ".";
      if (firstEnd && String(firstEnd).indexOf("none") < 0) {
        lead += " By day's end, the earliest entry still open was typically " + firstEnd + ".";
      }
    } else if (risk === "medium") {
      head = dow + "s fill up";
      lead = "Recent " + dow + "s ended around " + median + "% full. Morning entry times go first.";
    } else {
      head = dow + "s usually have room";
      lead = "Recent " + dow + "s ended around " + median + "% full — but advance tickets guarantee your entry time.";
    }

    var slots = "";
    var rates = a.slotSelloutRate || {};
    var keys = Object.keys(rates).sort();
    if (keys.length) {
      slots = '<ul class="trpl-tw-fslots">' + keys.map(function (t) {
        var r = rates[t];
        var f = r >= 0.6 ? "high" : r >= 0.3 ? "med" : "low";
        var w = r >= 0.6 ? "Usually sells out" : r >= 0.3 ? "Often sells out" : "Usually open";
        return '<li data-f="' + f + '"><b>' + esc(slotLabel(t)) + "</b><span>" + w + "</span></li>";
      }).join("") + "</ul>";
    }

    var daysOut = Math.round((Date.parse(dateIso) - Date.now()) / 864e5);
    var caveat = daysOut > FORECAST_CAVEAT_DAYS
      ? " Outlook is based on recent weeks — demand and hours vary by season." : "";

    return '<div class="trpl-tw-forecast" data-risk="' + risk + '"><h4>' + esc(head) + "</h4>" +
      "<p><strong>" + esc(prettyDate(dateIso)) + ":</strong> " + esc(lead) + "</p>" + slots +
      '<p class="trpl-tw-meta">Outlook based on the last ' + n + " " + esc(dow) + (n === 1 ? "" : "s") +
      " at the Library." + esc(caveat) + "</p>" +
      '<div class="trpl-tw-cta"><a class="trpl-tw-btn" href="' + esc(ticketsUrl) + '">Reserve This Day</a></div></div>';
  }

  function renderDateCheck(el, data, ticketsUrl) {
    var byDate = {};
    (data.days || []).forEach(function (d) { byDate[d.date] = d; });
    var today = data.today;
    var picked = el.getAttribute("data-picked") || today;

    el.innerHTML =
      '<div class="trpl-tw trpl-tw-datecheck"><h3>Check Your Date</h3>' +
      '<div class="trpl-tw-pick"><label for="trpl-dc-input">Planning to visit on</label>' +
      '<input type="date" id="trpl-dc-input" min="' + esc(today) + '" value="' + esc(picked) + '"></div>' +
      '<div class="trpl-tw-dc-result"><p class="trpl-tw-meta">Loading…</p></div></div>';

    var result = el.querySelector(".trpl-tw-dc-result");
    var input = el.querySelector("#trpl-dc-input");

    function show(dateIso) {
      el.setAttribute("data-picked", dateIso);
      if (dateIso < today) {
        result.innerHTML = "<p>That date has passed — pick a day ahead.</p>";
        return;
      }
      var day = byDate[dateIso];
      if (day) {
        if (day.closed) {
          result.innerHTML = '<div class="trpl-tw-forecast"><h4>Closed ' + esc(prettyDate(dateIso)) + "</h4>" +
            "<p>The Library is not open this day. Try a nearby date.</p></div>";
          return;
        }
        var riskLine = day.riskNote ? "<p><strong>" + esc(day.dayLabel === "Today" ? "Today" : prettyDate(dateIso)) +
          ":</strong> " + esc(day.riskNote) + "</p>" : "";
        result.innerHTML = riskLine + slotGridHtml(day) +
          '<div class="trpl-tw-cta"><a class="trpl-tw-btn" href="' + esc(ticketsUrl) + '">Reserve Tickets</a></div>' +
          '<p class="trpl-tw-meta">Live availability, Mountain Time.</p>';
      } else {
        result.innerHTML = '<p class="trpl-tw-meta">Looking at recent ' + esc(dowOf(dateIso)) + "s…</p>";
        getJson(el.getAttribute("data-analytics-url") || ANALYTICS_URL).then(function (analytics) {
          if (el.getAttribute("data-picked") === dateIso) {
            result.innerHTML = forecastHtml(dateIso, analytics, ticketsUrl);
          }
        }).catch(function () {
          result.innerHTML = forecastHtml(dateIso, null, ticketsUrl);
        });
      }
    }

    input.addEventListener("change", function () { if (input.value) show(input.value); });
    show(picked);
  }

  /* ---------------- year calendar heatmap (archive + live window) */

  function renderCalendar(el, data, ticketsUrl) {
    var base = (el.getAttribute("data-url") || DEFAULT_DATA_URL).replace(/availability\.json.*$/, "");
    var loadArchive = getJson(base + "archive/index.json")
      .catch(function () { return { months: [] }; })
      .then(function (index) {
        return Promise.all((index.months || []).map(function (m) {
          return getJson(base + "archive/" + m + ".json").catch(function () { return {}; });
        }));
      });
    var loadFuture = getJson(base + "future.json").catch(function () { return { days: {} }; });
    Promise.all([loadArchive, loadFuture]).then(function (results) {
      var monthFiles = results[0], future = results[1];
      var days = {};
      monthFiles.forEach(function (data2) {
        Object.keys(data2).forEach(function (d) {
          days[d] = { pct: data2[d].pctSold, soldOut: data2[d].fullySoldOut, kind: "final" };
        });
      });
      // Advance reservations for dates beyond the live window (through +1 year)
      Object.keys(future.days || {}).forEach(function (d) {
        var f = future.days[d];
        days[d] = { pct: f.pct, soldOut: f.slotCount > 0 && f.soldOutSlots >= f.slotCount, kind: "future" };
      });
      (data.days || []).forEach(function (d) {
        days[d.date] = d.closed ? { kind: "closed" } :
          { pct: d.pctSold, soldOut: d.selloutRisk === "sold_out", kind: "live" };
      });

      var today = data.today;
      var thisYear = +today.slice(0, 4);
      var years = {};
      Object.keys(days).forEach(function (d) { years[+d.slice(0, 4)] = 1; });
      years[thisYear] = 1;
      years = Object.keys(years).map(Number).sort();

      function color(rec) {
        if (!rec) return null;
        if (rec.kind === "closed") return "#fff";
        if (rec.soldOut || rec.pct >= 100) return "#092A4D";
        return rec.pct >= 90 ? "#E7805D" : rec.pct >= 70 ? "#FC924E" :
               rec.pct >= 40 ? "#8FC895" : rec.pct >= 1 ? "#EAF4EB" : "#F0EDE6";
      }

      var MONTHS = ["January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"];

      function draw(year) {
        el.setAttribute("data-year", year);
        var ghostCount = 0;
        var yearBtns = years.map(function (y) {
          return '<button aria-pressed="' + (y === year) + '" data-y="' + y + '">' + y + "</button>";
        }).join("");
        var months = "";
        for (var m = 0; m < 12; m++) {
          var nDays = new Date(year, m + 1, 0).getDate();
          var pad = (new Date(year, m, 1).getDay() + 6) % 7; // Monday-first
          var cells = ["M", "T", "W", "T", "F", "S", "S"].map(function (c) {
            return '<span class="dw">' + c + "</span>";
          });
          for (var i = 0; i < pad; i++) cells.push("<span></span>");
          for (var d = 1; d <= nDays; d++) {
            var iso = year + "-" + String(m + 1).padStart(2, "0") + "-" + String(d).padStart(2, "0");
            var rec = days[iso], cls = "dd", title = iso;
            if (rec) {
              title += rec.kind === "closed" ? " — closed" :
                " — " + rec.pct + "% reserved" + (rec.soldOut ? " (sold out)" : "") +
                (rec.kind === "live" ? " (live)" : rec.kind === "future" ? " so far (advance sales)" : "");
            }
            var ghostStyle = null;
            if (!rec && iso > today) {
              var ly = days[(year - 1) + iso.slice(4)];
              if (ly && ly.kind === "final") {
                cls += " ghost";
                ghostCount++;
                ghostStyle = "border-color:" + color(ly);
                title += " — not on sale yet · last year this date " +
                  (ly.soldOut ? "sold out completely" : "ended " + ly.pct + "% full");
              } else title += " — no data yet";
            } else if (!rec) title += " — no data";
            if (iso === today) cls += " today";
            var bg = ghostStyle ? null : color(rec);
            cells.push('<span class="' + cls + '"' +
              (bg ? ' style="background:' + bg + '"' : ghostStyle ? ' style="' + ghostStyle + '"' : "") +
              ' title="' + esc(title) + '"></span>');
          }
          months += '<div class="trpl-tw-cal-month"><h4>' + MONTHS[m] + " " + year +
            '</h4><div class="trpl-tw-cal-grid">' + cells.join("") + "</div></div>";
        }
        var legend = el.hasAttribute("data-hide-legend") ? "" :
          '<div class="trpl-tw-cal-legend">' +
          '<span><i style="background:#EAF4EB"></i>Quiet</span>' +
          '<span><i style="background:#8FC895"></i>Moderate</span>' +
          '<span><i style="background:#FC924E"></i>Busy</span>' +
          '<span><i style="background:#E7805D"></i>Very busy</span>' +
          '<span><i style="background:#092A4D"></i>Sold out</span>' +
          '<span><i style="background:#fff;border:1px solid rgba(37,40,42,.3)"></i>Closed</span>' +
          '<span><i style="background:#F0EDE6"></i>No data yet</span>' +
          '<span><i style="background:transparent;border:2px dashed #E7805D"></i>Last year\u2019s pattern (not on sale yet)</span>' +
          "</div>";
        el.innerHTML =
          '<div class="trpl-tw trpl-tw-cal">' +
          (el.hasAttribute("data-hide-heading") ? "" : "<h3>Reservation Calendar</h3>") +
          '<div class="trpl-tw-cal-years">' + (years.length > 1 ? yearBtns : "") + "</div>" +
          legend +
          '<div class="trpl-tw-cal-months">' + months + "</div>" +
          (ghostCount ? '<p class="trpl-tw-meta">Dashed outlines are not on sale yet \u2014 they show how full ' +
            "that date ended <strong>last year</strong>, as a planning guide only.</p>" : "") +
          (el.hasAttribute("data-hide-cta") ? "" :
            '<div class="trpl-tw-cta"><a class="trpl-tw-btn" href="' + esc(ticketsUrl) + '">Reserve Tickets</a></div>');
        el.querySelectorAll(".trpl-tw-cal-years button").forEach(function (b) {
          b.addEventListener("click", function () { draw(+b.getAttribute("data-y")); });
        });
      }
      draw(+(el.getAttribute("data-year")) || thisYear);
    }).catch(function (err) {
      if (window.console) console.warn("TRPL widget (calendar):", err);
    });
  }

  /* ------------------------------------------------ bootstrap */

  var RENDERERS = {
    alert: renderAlert,
    timeslots: renderTimeslots,
    planner: renderPlanner,
    datecheck: renderDateCheck,
    outlook: renderOutlook,
    calendar: renderCalendar
  };

  function initAll() {
    injectStyles();
    var nodes = document.querySelectorAll("[data-trpl-widget]");
    var refreshers = [];
    nodes.forEach(function (el) {
      var kind = el.getAttribute("data-trpl-widget");
      var render = RENDERERS[kind];
      if (!render) return;
      var url = el.getAttribute("data-url") || DEFAULT_DATA_URL;
      function refresh() {
        getJson(url).then(function (data) {
          // Non-destructive refresh: never re-render while the visitor is
          // interacting with this widget, and skip when data hasn't changed.
          // (A full innerHTML swap would destroy focus and can cause the
          // browser to jump/scroll.)
          if (el.contains(document.activeElement) && document.activeElement !== document.body) return;
          if (el.getAttribute("data-rendered") === String(data.generatedAt)) return;
          var ticketsUrl = el.getAttribute("data-tickets-url") || data.ticketsUrl ||
            "https://www.trlibrary.com/tickets";
          render(el, data, ticketsUrl);
          el.setAttribute("data-rendered", String(data.generatedAt));
        }).catch(function (err) {
          /* Fail quietly: never break the host page. */
          if (window.console) console.warn("TRPL widget (" + kind + "):", err);
        });
      }
      refresh();
      refreshers.push(refresh);
    });
    if (refreshers.length) {
      // One shared timer for all widgets (previously one per widget)
      setInterval(function () {
        cache = {};
        refreshers.forEach(function (fn) { fn(); });
      }, REFRESH_MS);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initAll);
  } else {
    initAll();
  }
})();
