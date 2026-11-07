# Preliminary-results HTTP experiment (#696)

## Method and observed environment

Executed November 6, 2026 on the authorized local executor, observed hostname
`officemini.local`, macOS 27.0.1 arm64. Commands used explicit working directories.
This does not reconstruct the unrecorded host/proxy context of the November 4 requests.

Tested these exact offered public resources:

- State: <https://results.votewa.gov/cdn/results/washington/export-20261103.json>
- County: <https://results.votewa.gov/results/public/api/elections/king-county-wa/20261103/data>

The local fixture exercised 200, redirect, 403 and dropped-connection responses before
the live matrix. The first fixture attempt exposed a TypeScript compilation mistake;
it was corrected before live requests. The complete fixture run accounted for 28
client/case observations and 32 loopback requests, including default redirect/failure
behavior. Fixture errors and the initial failed compilation remain in the run record.

The live matrix ran 18:19:50–18:19:59 UTC, one initial GET per client/resource: 14
transactions, no application retry. No user-agent spoofing, credentials, cookie transfer,
proxy/identity/host rotation or TLS-verification disabling. Normally redirect-following
clients used an explicit first-hop stop for the live experiment; no live redirects occurred.
Versions and selected response headers, timing, TLS observations, sizes and hashes are
retained in the original experiment records. Missing TLS/wire fields are unknown.

| Client | Observed version | State | County |
| --- | --- | --- | --- |
| Python urllib | Python 3.11.12 / OpenSSL 3.0.16 | 403 | 403 |
| Python urllib | Python 3.12.14 | 403 | 403 |
| Node core HTTPS | Node 22.14.0 | 200; body exceeded experiment cap | 200, full body |
| TypeScript using built-in fetch | TypeScript 7.0.2 / Node 22.14.0 | 200; body exceeded experiment cap | 200, full body |
| Node Undici request | Undici 7.30.1 / Node 22.14.0 | 200; body exceeded experiment cap | 200, full body |
| Ruby Net::HTTP | Ruby 3.4.4 / net-http 0.6.0 | 200; body exceeded experiment cap | 200, full body |
| bash / curl | bash 5.3.15 / curl 8.7.1 | 200, full body | 200, full body |

The four Python 403 bodies were the same 17 bytes, `error code: 1010` plus a newline,
SHA-256 `2938e9f1284180959e33ab1718d0793a72ff6e4cdb8108c34dcd14e69446de5c`.
All five successful County bodies were identical, 1,457,350 bytes, SHA-256
`f23cc84bf8266dd654dcbc7855b4f6e9e526ae0271062d3c070ea38680cfbbc9`.
The curl State body was 79,323,228 bytes, SHA-256
`e86704976a2f53b200f3f68e9a9f0d0748208beda7d491dd74d710fdaf4b9d9d`.

The Python/Node/Ruby experiment harness capped retained bodies at 20 MiB; the curl
output was time-bounded but not given that body cap. Therefore the other State 200s
establish successful HTTP access, not complete-body equivalence. Client-returned bytes
include native decoding where applicable; the TypeScript fetch County response used
Brotli encoding. TLS was verified by the clients; observed curl/Node/Ruby TLS connections
used TLS 1.3. No claim is made that every client used the same HTTP/TLS fingerprint.

## Actual application transport

The guide uses `http.client` with its existing identifying SEG user agent, not urllib.
After its 25-test offline baseline passed, one unchanged application request to the County
feed at 18:38:57 UTC returned 200 and the identical complete County body above.

The ordinary collector's 25 MiB cap cannot retain this State export. The results-only
profile shares the existing public-DNS/peer validation, TLS verification, total deadline
and response-integrity checks. It has a separate 128 MiB cap and refuses redirects.
The ordinary collection cap remains 25 MiB. Offline tests exercised the separate caps,
403 stop, redirect stop, non-public address refusal and deadline validation.

One actual `results acquire-preliminary statewide --live` run completed at 18:47:29 UTC.
It returned 200 and retained the complete State body, identical to curl's body above,
through the normal immutable evidence writer. The earlier genuine application County
response was also retained without another request. These two compatibility observations
bring the total to 16 initial live requests. There was no automatic client fallback.

## Conclusion and limits

Ordinary client behavior differs. A urllib 403 is not evidence that all clients or Python
are blocked: the existing application Python transport succeeded. The experiment did not
isolate whether headers, TLS/HTTP behavior, caching or publisher policy caused the difference.
It does not establish the publisher's intent, permanent availability or CI-runner access.

The implementation can use the existing Python runtime; adding a Node/Ruby/curl production
dependency is unnecessary on this evidence. A real subsequent denial must stop acquisition,
retain the failure and preserve previous counts; the producer must not rotate clients.

## Current data admission

The saved current bodies preserve all 52 historical contest identities and 83 named-choice
bindings. All 32 previously mapped State aggregate contests also retain their choice IDs/names.
State aggregate totals, rather than King County's slice, are required for statewide and
cross-county races such as LD32. These identity checks are not blanket geography approval.

County states `isOfficialResults: false` and count `asOf: 2026-11-06T18:00:47.2186345Z`.
State states `createdAt: 2026-11-06T18:15:56.2119008Z`; that is export generation, not a count
timestamp. It supplies no explicit certification status or count-as-of field. Do not transfer
County's status/clock to the State aggregate. Council District 5 still has a literal `Write-in`
row with `isWriteIn: false`; preserve the contradiction rather than silently reclassifying it.

Acquisition is implemented separately from admission, scheduling and protected publication.
No current production tally is admitted by this report. New timestamp wording awaits UI
approval, and the remaining status/scope/mapping decisions must be explicit and tested.
