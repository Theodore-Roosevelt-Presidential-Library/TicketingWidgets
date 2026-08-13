# TicketingWidgets

Embeddable JavaScript widgets that help visitors plan their trip to the Theodore Roosevelt Presidential Library — showing which timed-entry slots are sold out, warning when a day is likely to sell out, and suggesting better days to visit. Data comes from the ACME ticketing system's Reporting API, refreshed every 15 minutes by GitHub Actions and served as static JSON from GitHub Pages. No servers, no exposed API keys.

## How it works

```
ACME Reporting API ──(GitHub Action, every 15 min)──> data/availability.json
                                                            │
trlibrary.com/visit  <──(one <script> embed)── GitHub Pages CDN
```

1. `.github/workflows/update-availability.yml` runs on a 15-minute cron.
2. `scripts/fetch_availability.py` executes the "TRPL: 2026 Availability" report (definition `69c18975669b758620b4c586`), which returns one row per GA time slot with `EventStartTime`, `AvailableQuantity`, and `Capacity`. The date range is set dynamically each run (today → +7 days). The script computes sold-out status and sell-out risk (using sales pace from `data/history.json`) and writes `data/availability.json`.
3. GitHub Pages serves the JSON and `widgets/trpl-tickets.js` with permissive CORS, so the widgets work on trlibrary.com.

## The widgets

Add the script once per page, then drop in any container:

```html
<script src="https://ticketing.labs.trlibrary.com/widgets/trpl-tickets.js" defer></script>

<!-- Sell-out alert banner (homepage / tickets page) -->
<div data-trpl-widget="alert"></div>

<!-- Today + next 2 days time-slot grid -->
<div data-trpl-widget="timeslots"></div>

<!-- Week-ahead "best days to visit" planner -->
<div data-trpl-widget="planner"></div>

<!-- Date picker: live slots for the next 8 days, day-of-week forecast beyond -->
<div data-trpl-widget="datecheck"></div>

<!-- Month outlook: narrative text ("what we're seeing this month and what to expect") -->
<div data-trpl-widget="outlook"></div>
```

**Month outlook** renders a short narrative composed by the pipeline each run from live sales data (e.g. "August has been busy: over the last 15 days, daily ticket sales reached a median 94% of capacity. Mornings go first…"). Supports `data-hide-heading` and `data-hide-cta`.

**Reservation calendar** — [/calendar.html](https://ticketing.labs.trlibrary.com/calendar.html) is a year-at-a-glance heatmap of how full each day has been, drawn from the permanent archive plus the live window. It starts sparse (collection began August 2026) and fills in daily; once the archive holds a prior year, future dates show last year's same-date pattern as a ghost overlay for planning around historically busy stretches.

**Check Your Date** lets a visitor pick any future date. Inside the live window it shows real slot availability; beyond it, it forecasts from recent day-of-week behavior ("Saturdays have been selling out — by day's end the earliest entry still open was typically 1:00 PM") with a per-slot outlook strip, plus a seasonality caveat for dates more than ~45 days out.

### Floating sell-out banner (Google Tag Manager)

Sitewide banner docked lower-left. Shows only when there's something worth saying (medium+ risk or sold-out slots); dismissing hides it for the rest of the Mountain-Time day across all pages (localStorage). Stays silent if data is stale. Install as a GTM Custom HTML tag on All Pages:

```html
<script>window.TRPL_FLOAT = { minRisk: "medium" };</script>
<script src="https://ticketing.labs.trlibrary.com/widgets/trpl-float.js" async></script>
```

Options via `window.TRPL_FLOAT`: `minRisk` ("low" | "medium" | "high"), `ticketsUrl`, `dataUrl`. Consider a GTM trigger exception on the tickets page itself.

### Styling

Widgets match the TRPL Brand Identity System as implemented on trlibrary.com (verified against the live theme): buttons are Frutiger bold, sentence case, Deep Orange `#E7805D` with Dark Gray `#25282A` text and 2px radius — identical to the site's Tickets/Donate buttons; section headers are Frutiger bold uppercase; big headlines (alert banner) are Dharma Gothic E uppercase in Night Sky `#092A4D`. Guide colors only: Bright Forest `#8FC895` (available), Sunset Orange `#FC924E` (filling up), Deep Orange (high risk accents), Night Sky (sold out), Sand `#D1CCBD` surfaces. trlibrary.com self-hosts the fonts under family names `Clearface`, `Dharma Gothic E`, and `Frutiger` — all present in the widget font stacks, so the real fonts render automatically on the site with no extra loading. For off-site embeds without the fonts, pass a font CSS URL via `data-fonts-css` on the script tag (or `window.TRPL_FONTS_CSS`; for the float banner, `TRPL_FLOAT.fontsCss`). Override via CSS variables on any ancestor: `--trpl-tw-display`, `--trpl-tw-body`, `--trpl-tw-caption`, `--trpl-tw-cta`, `--trpl-tw-forest`, `--trpl-tw-night`, `--trpl-tw-bright`, `--trpl-tw-sand`, `--trpl-tw-warn`, `--trpl-tw-border`. Optional attributes per container: `data-url`, `data-tickets-url`, and `data-hide-cta` to hide the Buy Tickets button (alert, timeslots, and planner) — e.g. `<div data-trpl-widget="planner" data-hide-cta></div>`. Widgets self-refresh every 5 minutes and fail silently if data is unreachable — they will never break the host page.

Preview everything at [https://ticketing.labs.trlibrary.com](https://ticketing.labs.trlibrary.com); staff monitor at [https://ticketing.labs.trlibrary.com/monitor.html](https://ticketing.labs.trlibrary.com/monitor.html).

## One-time setup

1. **Get an ACME API key.** API keys are tied to an ACME user. Have your ACME Backoffice admin create a username-only integration user (e.g. `api-website-widgets`) with permission to run reports, then — as an ACME client — submit the "Requesting an API Key" checklist to ACME Product Support (see [ACME's guide](https://developers.acmeticketing.com/support/solutions/articles/33000248661-working-with-acme-apis)). While waiting, a temporary session key (`GET /v2/b2b/customer/session`) can be used for testing only.
2. **Add the secret.** Repo → Settings → Secrets and variables → Actions → New repository secret: `ACME_API_KEY`. Optional repository *variables*: `ACME_REPORT_ID` (defaults to `69c18975669b758620b4c586`), `ACME_API_BASE` (defaults to production; use a sandbox URL for testing). The report's date range is set dynamically by the script — no Backoffice changes needed.
3. **Enable GitHub Pages.** Repo → Settings → Pages → Deploy from branch → `main` / root. The custom domain `ticketing.labs.trlibrary.com` is set via the `CNAME` file — add a DNS CNAME record pointing it to `theodore-roosevelt-presidential-library.github.io` and enable "Enforce HTTPS".
4. **Run it.** Actions → "Update availability data" → Run workflow. Check `data/availability.json` and the demo page.

Until a key is added, the script runs in mock mode and generates plausible sample data, so the widgets and demo page work end to end.

## Where the numbers come from

Slot times, remaining tickets, and per-slot capacity all come live from the ACME report — no hardcoded assumptions. A date with no GA event instances renders as "Closed." The seasonal-hours block in `config.json` is only used by mock mode (when no API key is present); thresholds for "few left" labeling (`limitedThresholdPct`/`limitedThresholdMin`) also live there.

## Sell-out prediction & the walk-up problem

Percent-sold alone is misleading: a day can sit at 60% sold the night before and still sell out mid-morning from walk-up demand. Risk is therefore modeled as **supply vs. expected demand for that weekday**:

- Each run also pulls the past `lookbackDays` (15) from ACME and archives every completed day permanently to `data/archive/YYYY-MM.json`: final sell-through, which slots ended sold out, observed sell-out clock times, lead curve (pct sold at each days-out), and same-day ticket count. This archive grows forever — year-over-year comparisons become possible as it accumulates.
- `data/analytics.json` summarizes the lookback window per day of week: median final sell-through, full-sellout rate, per-slot sell-out frequency, typical first entry still open at end of day, and median same-day (walk-up + day-of online) tickets.
- **Future days:** if recent same-weekday days sold more tickets on the day itself than this day has remaining, or the weekday routinely ends ≥90% sold, risk is high regardless of current percent — with concrete copy like "Saturdays have been selling out — recently only 1:00 PM or later entry remained."
- **Today:** projected sell-out time uses the *greater* of observed pace (last 3h of 15-min snapshots in `data/history.json`) and typical same-day demand for the weekday.
- Same-day demand and intraday sell-out times need running snapshots, so those signals mature over the first 1–2 weeks; final-outcome analytics were bootstrapped from ACME immediately.

Tune thresholds in `day_risk()` in `scripts/fetch_availability.py`.

## Internal monitoring

`monitor.html` (noindex, staff-facing — same Pages site) shows the next 8 days with risk and notes, per-day-of-week behavior cards (median sell-through, sellout counts, per-slot sell-out heat strip, same-day demand), and the last 15 days of outcomes.

## Repo layout

```
config.json                       thresholds, tickets URL, mock-mode hours
scripts/fetch_availability.py     ACME API client + transform (stdlib only)
.github/workflows/update-availability.yml
widgets/trpl-tickets.js           embedded widgets (alert, timeslots, planner, datecheck)
widgets/trpl-float.js             floating GTM banner, dismissible per day
data/availability.json            generated — consumed by widgets
data/history.json                 generated — rolling 72h snapshots (intraday pace)
data/leads.json                   generated — pct sold at each days-out lead time
data/analytics.json               generated — day-of-week sell-out behavior
data/archive/YYYY-MM.json         generated — permanent per-day outcomes (YoY)
data/raw-report.json              generated — last raw ACME response (debugging)
index.html                        demo page (served by Pages)
monitor.html                      internal sell-out monitor (staff)
```

## Notes & caveats

- The parser has been validated against live ACME output (columnar `resultFieldList` with `EventStartTime` / `AvailableQuantity` / `Capacity`). If the report structure ever changes, the Action fails loudly rather than publishing wrong numbers; check `data/raw-report.json`.
- Times displayed are Mountain Time (`America/Denver`), matching Medora.
- GitHub's cron can drift 5–15 minutes under load; the widgets show "Updated X min ago" and soften their language if data is more than 90 minutes old.
- The API key grants whatever its ACME user can do — scope that user to reporting only.
