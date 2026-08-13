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

