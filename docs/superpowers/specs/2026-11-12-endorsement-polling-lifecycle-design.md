# Endorsement polling lifecycle (#748)

Endorsement-source monitoring ends after the election. A DNS failure is retained evidence of an inaccessible source, not a release blocker or a request to repair the publisher's DNS.

The existing link-check command fetches unconditionally. Its daily workflow hardcodes the general-election registry; the later alert reconciliation interprets an empty result as healthy. In contrast, endorsement collection already stops new due work after election day.

Use the existing strict election calendar and America/Los_Angeles timezone. Resolve the scheduled registry from the site's current election, validate that identity against its calendar election, then return an explicit skipped outcome on the first Pacific day after election day. This happens before source fetching, reading or writing failure state, and alert reconciliation. Missing or malformed identities fail before requests. Election-day checks retain normal confirmation and access-control semantics. There is no backdating or force option.

The workflow must save a cache only when the command actually wrote state. A skipped or dry run preserves historical failures and does not claim recovery. Retire the existing #748 alert explicitly after the correction is delivered; preserve its original failure and state that closure means monitoring retired, not DNS repaired. Repeated closed-period invocations produce no additional alerts or comments.

Alternatives considered: removing the cron would also disable future elections; hardcoding a November cutoff would duplicate the calendar and fail the next cycle. The calendar guard and current-election selection are the smallest reusable correction. This is the implementation choice under the already supplied scope, with the same sole root owner.

Change only the CLI, scheduled link workflow, focused tests and the two policies that currently imply indefinite retries. Do not alter accepted endorsements, citations, calendars, historical missed slots, shared HTTP transport, official results acquisition, certification, CI integrity gates or production acceptance. Keep PR744's checkout frozen. The isolated maintenance checkout starts at its merged source; normal preparation uses the actual published catalog and fresh version selection. External maintenance delivery stays serialized after PR744 protected acceptance.
