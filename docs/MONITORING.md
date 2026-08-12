# Traffic monitoring

Investigation for #217 (O9), part of epic #205. Explicitly rejects Google Analytics: cookie-based
tracking would obligate a consent banner on a nonpartisan voter guide, and it would hand
voter-interest data to an advertising company. Cloudflare's zone analytics is cookieless, requires
no client-side code, and needs no consent banner — it counts every request the edge serves,
including the ones a client beacon never sees.

## Where it lives

Cloudflare dashboard → account → the `seattleelections.guide` zone (Free plan) → **Analytics**
in the left sidebar. Two views expose the same underlying request data:

- **HTTP Traffic** (`Analytics → HTTP Traffic`) is Cloudflare's built-in report: total/cached/
  uncached requests, bandwidth, unique visitors, and a requests-by-country map, each over a
  24-hour/7-day/30-day window.
- **Dashboards** (`Analytics → Dashboards`) is a custom-chart builder against the same
  `HTTP Requests` dataset, and is where the useful breakdowns live. A dashboard named
  **Traffic overview** already exists in this account (created 2026-08-04) with 17 charts:
  total requests, total visits, cache hit rate, data transfer, requests over time, requests by
  device type, requests by country, status codes, top paths, top hosts, and top client IPs (plus
  top browsers/OS/user agent/HTTP version/cache status/origin status code, which currently read
  "No data" — see below). To build an equivalent chart from scratch: **Add a chart → Top List →
  HTTP Requests → Metric: Requests - Total → Group by:** `Path`, `Country`, `Edge status code`,
  etc.

## What it can answer

Confirmed live against production on 2026-08-11 (Previous 24 hours, 506 total requests):

- **Request volume and visitors.** 506 requests, 50 visits, 31.82% cache hit rate, 7.5 MB
  transferred.
- **Status codes**, down to the exact code via `Group by: Edge status code` — not just the 2xx/
  3xx/4xx/5xx buckets the Traffic overview dashboard shows by default. A 12-hour sample read: 200
  OK 145, 404 Not Found 72, 307 Temporary Redirect 29, 204 No Content 17, 403 Forbidden 13, 301
  Moved Permanently 11, 304 Not Modified 2. The 307/301 codes are the edge-generated redirects
  documented in `docs/HOSTING.md` (the `/`, slashless-path, legacy-host, and retired-PDF-path
  rules); the 304s are conditional-GET responses from the site's `Cache-Control: public,
  max-age=0, must-revalidate` policy (`src/election_guide/hosting/pages.py`), not redirects. Both
  kinds are edge-level responses that never execute page JavaScript or fire a client beacon — the
  3xx bucket as a whole, not only its redirect share, is something no client beacon can observe.
- **Top paths**, including non-HTML assets a client beacon cannot observe because no page ever
  renders: `/favicon-32.png` (60), `/robots.txt` (29), `/apple-touch-icon.png` (23),
  `/favicon.ico` (19), `/sitemap.xml` (16), `/og-image.png` (43), alongside HTML paths like `/`
  (110) and `/e/wa-2026-primary/` (63).
- **Top hosts** and **top client IPs**. The sample window's top hosts were
  `seattleelections.guide` (478) and `www.seattleelections.guide` (28) — but `www` is not a
  documented or intentional site host. It is not in `docs/HOSTING.md`'s custom-domains list, not
  in the worker's `LEGACY_HOSTS` (`src/election_guide/hosting/pages.py`), and not attached to the
  Pages project; DNS shows it as a separate, proxied `A` record pointing to a static IP unrelated
  to `seattle-elections.pages.dev`. Zone analytics counts its traffic because Cloudflare proxies
  it, not because it's part of this site's hosting configuration — worth a look under the hosting
  epic (#202/#203), not something this ticket resolves.
- **Country and device-type breakdown** (Desktop 299, Mobile 207, Tablet 0 in the sample window).

This satisfies the ticket's acceptance criterion directly: request counts for paths and response
types no client beacon can observe — redirects and non-HTML assets — are demonstrably obtainable
from zone analytics alone, with no code changes.

## What it cannot answer

- **Referrers are not available.** The `HTTP Requests` dataset's full group-by list was checked
  in the chart builder: `Country`, `Source device type`, `Source IP`, `Host`, `HTTP method`,
  `HTTP version`, `Path`, `SSL Protocol`, `Content type matched`, `Edge status code`,
  `Origin status code`, `Source user agent`, `Source browser`, `Source operating system`, and a
  handful of security/bot fields — no referer/referrer field exists anywhere in it. Zone
  analytics cannot answer "where did visitors come from." (The original epic's outcome statement
  listed referrers among the expected fields; that expectation does not hold for this dataset on
  this plan.)
- **Browser, OS, user agent, HTTP version, cache status, and origin status code** charts are
  present in the chart library but currently show "No data" in the existing Traffic overview
  dashboard. Cause not diagnosed — possibly a population lag, possibly a Free-plan restriction on
  those specific groupings. Worth rechecking once more traffic has accumulated.

## Retention

The dashboard's own selector caps at **Previous 30 days** (24 hours / 7 days / 30 days are the
only choices), and a live check confirmed the 30-day window populates with real data back to
mid-July — 30.3k requests total. Cloudflare's public docs do not publish a plan-specific
retention table for the `httpRequestsAdaptiveGroups` dataset this view queries (the one concrete
number found, 16 weeks, is for the unrelated Enterprise-only Network Analytics product), so 30
days is the only retention figure confirmed for this account.

**Decision: 30 days is too short to span an election cycle**, and history needs exporting if
cross-cycle trend data is wanted. The primary (2026-08-04) and general (2026-11-03) elections are
roughly 13 weeks apart — well past what the dashboard window retains. Per this ticket's scope,
that export is not built here: the follow-up is a scheduled pull against the GraphQL Analytics
API (same `httpRequestsAdaptiveGroups` dataset, queryable with a scoped API token) that archives
daily rollups before they age out of the dashboard's window.

## Client-side beacon (O10, not this ticket)

`Analytics → Web analytics` is already collecting real Core Web Vitals data (LCP/INP/CLS) for
specific `/e/wa-2026-primary/...` page URLs, and `/cdn-cgi/rum` shows up in the zone's top-paths
report. Whether this is Cloudflare Pages' automatic beacon injection or something else, and
whether it's compatible with the artifact-integrity chain described in #205, is #218's
investigation, not this ticket's — noted here only because it bears on "what traffic data lives
where."
