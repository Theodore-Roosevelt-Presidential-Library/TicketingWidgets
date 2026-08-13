# Structured Data Spec: Hours for trlibrary.com

**For:** web team (Drupal `trpl` theme / metatag config)
**Status:** proposed — August 2026
**Why:** The site's JSON-LD `Museum` entity already includes holiday closures (`specialOpeningHoursSpecification`) but no regular weekly hours. Search engines, map services, and AI assistants can currently see when the Library is closed but not when it is open. Adding seasonal `openingHoursSpecification` blocks fixes that, improves Google Business Profile / rich-result accuracy, and gives internal tools (ticketing widgets pipeline) a canonical machine-readable hours source to cross-check against ACME.

## What to add

Merge the following into the existing `@graph` Museum entity (keep all current properties — name, address, geo, sameAs, and the existing `specialOpeningHoursSpecification` holiday closures). Times are 24-hour local (Mountain Time). Days omitted from a block are closed that season; holiday closures stay in `specialOpeningHoursSpecification`, which overrides the weekly pattern.

```json
{
  "@type": ["Museum", "Library", "TouristAttraction"],
  "isAccessibleForFree": false,
  "tourBookingPage": "https://www.trlibrary.com/tickets",
  "openingHoursSpecification": [
    {
      "@type": "OpeningHoursSpecification",
      "description": "Spring hours",
      "dayOfWeek": ["Tuesday", "Wednesday", "Thursday", "Friday"],
      "opens": "10:00",
      "closes": "16:00",
      "validFrom": "2026-03-02",
      "validThrough": "2026-05-31"
    },
    {
      "@type": "OpeningHoursSpecification",
      "description": "Spring weekend hours",
      "dayOfWeek": ["Saturday", "Sunday"],
      "opens": "10:00",
      "closes": "17:00",
      "validFrom": "2026-03-02",
      "validThrough": "2026-05-31"
    },
    {
      "@type": "OpeningHoursSpecification",
      "description": "Summer hours",
      "dayOfWeek": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
      "opens": "09:00",
      "closes": "18:00",
      "validFrom": "2026-06-01",
      "validThrough": "2026-09-13"
    },
    {
      "@type": "OpeningHoursSpecification",
      "description": "Fall hours",
      "dayOfWeek": ["Tuesday", "Wednesday", "Thursday", "Friday"],
      "opens": "10:00",
      "closes": "16:00",
      "validFrom": "2026-09-14",
      "validThrough": "2026-11-30"
    },
    {
      "@type": "OpeningHoursSpecification",
      "description": "Fall weekend hours",
      "dayOfWeek": ["Saturday", "Sunday"],
      "opens": "10:00",
      "closes": "17:00",
      "validFrom": "2026-09-14",
      "validThrough": "2026-11-30"
    },
    {
      "@type": "OpeningHoursSpecification",
      "description": "Winter hours",
      "dayOfWeek": ["Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
      "opens": "10:00",
      "closes": "16:00",
      "validFrom": "2026-12-01",
      "validThrough": "2026-12-31"
    }
  ]
}
```

## Open questions for the team

1. **January–March 1 hours** are not published on /visit — confirm the early-winter schedule and add a matching block (`validFrom: 2027-01-01`, `validThrough: 2027-03-01`).
2. **Season dates roll annually.** `validFrom`/`validThrough` are year-specific, so this markup needs a yearly refresh when the season calendar is set — ideally driven from the same Drupal content that renders the /visit hours tabs, not hand-edited JSON.
3. **Last entry vs. closing.** `closes` should be building close (6 PM summer), not last timed-entry slot (5 PM). Confirmed above on that assumption.

## Keep as-is

The existing `specialOpeningHoursSpecification` holiday closures (Christmas, New Year's Eve, Thanksgiving, Friends and Family Day) follow the correct pattern — `opens: 00:00, closes: 00:00` with `validFrom`/`validThrough` on the date. Add each year's dates as they're scheduled.

## Validation

After deploying: Google Rich Results Test (search.google.com/test/rich-results) and Schema.org validator (validator.schema.org) against https://www.trlibrary.com/visit/hours. Then confirm Google Business Profile hours still match — GBP hours are managed separately and should agree with the markup.

## Bonus once live

The ticketing widgets pipeline (this repo) can read this markup on each run and flag mismatches between published hours and ACME's event instances — e.g. a slot accidentally on sale after closing, or a day ACME thinks is open that the site says is closed.
