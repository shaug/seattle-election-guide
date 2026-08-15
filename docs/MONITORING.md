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
  documented in `docs/HOSTING.md` (`/` is a 307 to the current election; legacy hosts and the
  retired PDF path are 301s). Slashless paths are a separate redirect rule and a permanent `308`
  rather than a 307 or 301 — none appeared in this particular sample window. The 304s are
  conditional-GET responses from the site's `Cache-Control: public,
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
  it, not because it's part of this site's hosting configuration — worth a look under #227 (O19,
  "Document credential and hosting ownership," part of epic #207), which already scopes DNS
  dependencies; not something this ticket resolves.
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

## Client-side beacon (O10)

**Answer: Cloudflare Pages' automatic Web Analytics beacon injection works for this project's
advanced-mode `_worker.js`, and it is already enabled and reporting.** No repository change was
needed, so the worker-side-injection question this ticket raised — and the auditability trade-off
attached to it — never had to be decided.

`Analytics → Web analytics` (dashboard, not the zone-level `HTTP Traffic` view O9 documented)
lists a site for `seattleelections.guide`, created 2026-07-22, with **Automatic setup** and Real
User Measurements set to **"Enable, excluding visitor data in the EU"** — meaning Cloudflare
injects the beacon `<script>` itself; nothing in this repository requests or renders it.

That configuration predates this ticket, so the open question was whether it actually still works
now that the site ships an advanced-mode `_worker.js` that owns every response. Two checks
resolved it:

- **`curl` (even with a spoofed Chrome user agent, cache-busted, from a non-EU US IP) never
  receives the beacon.** Checked against `/`, `/about/`, and `/e/wa-2026-primary/`. The response
  does contain other Cloudflare edge-injected content on the same request — the
  `/cdn-cgi/scripts/.../email-decode.min.js` tag from Email Address Obfuscation — proving the edge
  still rewrites this worker's HTML in flight; the beacon specifically is just absent.
- **A real Chrome session loading the same URL does receive it.** DOM inspection showed a
  `<script src="https://static.cloudflareinsights.com/beacon.min.js/...">` tag, and the page fired
  a request to it. The likely explanation is that Cloudflare's RUM injector skips requests it
  scores as non-browser/bot traffic — unsurprising for a bare `curl`, spoofed UA notwithstanding —
  rather than skipping the worker's responses generally.

So the mechanism does work through the advanced-mode worker; only synthetic, bot-scored requests
miss it. Live data confirms it, last 21 days (2026-07-25 to 2026-08-15, bots excluded):

- **2.24k visits, 3.25k page views**, broken down per page URL (top: the primary election's
  comparisons page, individual race pages, `/about/`).
- **Referrers**: None/direct 1.27k, self-referral (internal navigation) 1.01k, `l.threads.com` 920,
  `www.bing.com` 10, `search.yahoo.com` 10. This is the one dimension O9's zone analytics could not
  answer at all — RUM fills exactly that gap, and surfaces Threads as a real, previously invisible
  traffic source.
- **Device mix**: Mobile ~2.28k, Desktop 960, Tablet 10.
- **Country**: United States 3.24k, Canada 10 — negligible EU traffic today, so the "excluding
  visitor data in the EU" setting has no material effect on current coverage.
- **Core Web Vitals** (LCP/INP/CLS): Good on all three, consistent with O9's separate finding that
  `Analytics → Web analytics` was already surfacing real vitals data before this investigation.

**On the auditability concern.** The ticket's caution against worker-side injection was that
`hosting verify`'s hash checks cover the staged bundle this repository builds and uploads, so a
worker that rewrote HTML in flight would make served bytes diverge from anything the manifest
attests to. Cloudflare's own automatic beacon injection has the same effect on served bytes — it
just isn't code this repository authors, ships, or reviews. `hosting verify` was never able to
attest to what Cloudflare's edge does to a response after it leaves this repository's build
output; Email Address Obfuscation was already proof of that before this ticket. Automatic Web
Analytics doesn't narrow that boundary any further, so it didn't need the same explicit yes/no as
writing the equivalent behavior into `_worker.js` would have.

No change to rendered guide output was made or is needed in either outcome.
