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
  `seattleelections.guide` (478) and `www.seattleelections.guide` (28). `www` resolves to the same
  Cloudflare anycast addresses as the apex, not a separate static IP, but at the time of this
  sample it was attached to neither the Pages project nor a redirect rule, so Cloudflare's edge
  accepted the connection and had nothing to serve it — the incomplete configuration issue #382
  fixed. `www` is now in `docs/HOSTING.md`'s custom-domains list and the worker's `LEGACY_HOSTS`
  (`src/election_guide/hosting/pages.py`), routed to canonical the same way as the other legacy
  hosts.
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
  **Rechecked 2026-08-16 — all six now carry data; see below.**

### The “No data” groupings, rechecked

Checked 2026-08-16 against the GraphQL Analytics API rather than the dashboard: the adaptive
dataset for 2026-08-14, and the daily dataset for the fortnight ending 2026-08-15. Every one of
the six returns rows, so the earlier emptiness was a population lag rather than a plan
restriction (issue #381).

- **Browser** — populates. 21 families over the fortnight; the largest single bucket is
  `Unknown`, ahead of the named mobile and desktop families.
- **Operating system** — populates. Six values for one day, again with `Unknown` largest.
- **User agent** — populates. Twelve distinct strings for one day, including a declared
  social-media link-preview crawler.
- **HTTP version** — populates. Four values over the fortnight: HTTP/3 leads at 8.6k requests,
  then HTTP/2 at 6.3k, HTTP/1.1 at 5.4k, and a residue of HTTP/1.0.
- **Cache status** — populates. Five values for one day, led by `dynamic`, then `revalidated`
  and `none`.
- **Origin status code** — populates. Six values for one day. A `0` bucket leads it, which is
  what the edge records when it answered without consulting the origin at all.

**None of the six is archived, and three of them never will be.** Browser, operating system, and
user agent are excluded on privacy grounds whatever they contain: this repository is public, so a
committed identifier is unretractable from every fork. The other three — HTTP version, cache
status, and origin status code — are merely out of scope for #381; they are the candidates if the
archived field set is ever widened. Note that all three of those live only in the eight-day
adaptive dataset, so adding them later would capture them going forward and could not backfill.

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

### Correction: the API's window is not the dashboard's

Two things above are wrong, discovered on 2026-08-16 while building that export (#381) and left
in place because the reasoning they led to is still worth reading.

**The dashboard and the API do not share a retention window, and the dashboard does not query
`httpRequestsAdaptiveGroups`.** Measured by walking the boundary a day at a time:

| | `httpRequestsAdaptiveGroups` | `httpRequests1dGroups` |
| --- | --- | --- |
| Retention on this zone | **8 days** | ~30 days |
| Past the edge | hard `quota` error | empty result |
| Path, device type | yes | **no** |
| Country, edge status code | yes | yes |
| Totals | `count`, `visits` | `requests`, `pageViews`, `uniques` |
| Sampled | yes (`sampleInterval`) | no, pre-aggregated |

So the 30-day figure belongs to `httpRequests1dGroups`, which is what the dashboard's 30-day
selector reads. The dataset with the useful breakdowns keeps eight days, and refuses older ones
outright rather than returning nothing.

**This was already too late for the richest form of the primary.** By the time the export was
built, 2026-08-04 was twelve days old and permanently beyond the adaptive window, so no path or
device-type breakdown for election day exists or can ever be recovered. Its totals, country
split, and status-code split were archived from the daily dataset with about eighteen days to
spare. The deadline was real; only the dataset was misidentified.

One more correction, minor: **referrers are available after all.** The claim above that no
referrer field exists anywhere came from the dashboard's chart builder. The adaptive dataset
exposes `clientRequestReferer` and `clientRefererHost`. They are not archived — out of scope for
#381 — but "zone analytics cannot answer where visitors came from" is untrue of the API, and only
the last eight days of it are ever reachable.

The export itself is now built — see [The archive](#the-archive).

## The archive

`data/analytics/<YYYY-MM-DD>.json` holds one file per UTC day. Tracked, not ignored —
`data/raw/`, `data/snapshots/`, and `data/imports/` are gitignored, and an ignored path is exactly
how the 2026-08-04 election-night capture bytes were lost (#357).

```bash
uv run election-guide analytics export                     # every missing in-window day
uv run election-guide analytics export --date 2026-08-14   # exactly one day
```

**Every day carries both datasets' answers where both are reachable.** The daily dataset is the
base — totals, country, and edge status code, for roughly thirty days back. The adaptive dataset
adds `visits`, `by_path`, and `by_device_type` for the eight days it still covers. `sources`
records which of the two answered, and the three adaptive-only fields are `null` — not empty — on
older days: empty would claim the site served no paths that day, whereas `null` says the question
was no longer answerable. **A day therefore gets richer only if it is archived within eight
days**, which is the strongest argument for the schedule staying healthy.

One command serves both the one-time backfill and the daily schedule, because they are the same
operation: ask which in-window days are missing, fetch those, write them. Three consequences worth
knowing:

- **A missed schedule repairs itself, but degrades.** The next run archives every day it lacks,
  not just yesterday, so no day is ever skipped outright. A day recovered more than eight days
  late is archived without its path and device-type breakdown, permanently.
- **Re-running is free and byte-stable.** An already-archived day is never fetched again, so
  re-running leaves its file byte-identical. That holds by construction rather than by assuming
  Cloudflare returns identical aggregates for a past day forever. It also means a thin day is
  never later enriched — the file is written once.
- **Today is never archived.** A day still accumulating would record a partial count and then
  never be revisited, so the newest candidate is always yesterday.

The first backfill ran on 2026-08-16 and archived 2026-07-22 through 2026-08-15 — 25 days, no
gaps. The run's own window floor was 2026-07-17, so the five days below 2026-07-22 returned
nothing and were skipped rather than recorded as zero-traffic days.

Why those five were empty is not determinable: an aged-out day and a day with no traffic give the
same empty answer, and the zone's own data appears to begin around 2026-07-22, which would also
explain it. Both readings are consistent with what the API returned, so the archive skips rather
than guesses — a zero would have been a claim about the site that nothing supports. The days are
now outside every window, so nothing is recoverable either way.

### How an archived day reaches `main`

`main` is protected and requires review, so the scheduled run cannot push to it
(`CONTRIBUTING.md`, "Do not commit directly to `main`"). It commits to an `analytics-archive`
branch, pushes there, and opens one pull request that later runs reuse — so a week of daily runs
accumulates into one reviewable pull request rather than seven.

**That pull request will not start CI on its own, and a maintainer has to nudge it.** GitHub
deliberately starts no workflow run for an event triggered by `GITHUB_TOKEN`, and `ci.yml` fires
only on `pull_request`, on pushes to `main`, and on manual dispatch. Closing and reopening the
pull request — or pushing any commit to the branch — starts the required `check`. The pull
request's own body says so.

This is a required-status-check formality rather than unreviewed content: the archive workflow
runs `tests/test_analytics.py` against the new days *before* it commits them, so the
committed-tree guards — no identifying value, no gaps — have already passed in the run that wrote
them. Doing it the other way round is what would hurt. If detection waited for CI, a value that
tripped a guard would already be on `main`, and every later pull request would inherit the failure.

The upgrade, if the nudge ever becomes annoying: give the pull-request step a fine-grained
personal access token or a GitHub App installation token instead of `GITHUB_TOKEN`, and inventory
it in `docs/HOSTING.md` beside the other credentials. That is a second credential to rotate, which
is why it was not taken by default.

The credential is `CLOUDFLARE_ANALYTICS_TOKEN`, scoped to **Zone / Analytics / Read**, with
`CLOUDFLARE_ZONE_ID` naming the zone — both inventoried in `docs/HOSTING.md`. A missing or
unauthorized token fails the run non-zero and writes nothing, rather than committing an empty
archive that would look like a day of no traffic.

### What is deliberately not archived

`Source IP`, `Source user agent`, and `Source browser` are excluded and must stay excluded. This
repository is public, so committed visitor-identifying data would be permanent and unretractable
from every fork of it, and it would contradict epic #205's stated posture. The exclusion is
structural rather than a filter: the export never requests those dimensions, and the archive model
rejects any field outside the vetted set, so storing one would require deleting that rule in a
visible diff.

**Request paths are stored verbatim, and that is not an exception to the above.** `by_path`
records the URL somebody asked for, which is the requester's own choice and says nothing about any
visitor. It matters because the zone is scanned continuously — 271 of the 640 paths archived so
far are probes like `/.aws/credentials` — so the archive is full of strings no human chose. An
earlier revision screened stored values against address- and user-agent-shaped patterns; it was
removed, because against `by_path` such a screen can only produce false positives, and a false
positive would have skipped the day, left a hole, and tripped the no-gaps check inside the
workflow's own pre-commit gate — stopping the archive from advancing at all. Structure, not
pattern-matching, is what keeps visitor data out.

### One condition that needs a human

The export can only archive days inside the retention window, so a schedule outage longer than
thirty days leaves the missed days permanently unarchivable. The next successful run then writes
a block of recent days that is not contiguous with the committed tail, and
`test_committed_archive_has_no_gaps` fails — first in the workflow's pre-commit step, which stops
the archive committing, and then in `make check` for the repository as a whole.

This is deliberate rather than papered over: a gap in a public audit trail should be explained by
a person, not silently tolerated by a check. Resolving it means deciding what the archive should
say about days nobody can recover, and recording that decision — which is a change to this
document and to the test, not something the exporter can invent on its own. Thirty consecutive
failed runs is the trigger, and the workflow's own guidance ("treat a week of red runs as urgent")
is meant to make it unreachable.

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
