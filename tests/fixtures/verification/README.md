These abbreviated, factual HTML fixtures represent the six current general-election
mappings reviewed by shaug in #474. They retain names, offices, publisher spelling
variants, and dual endorsements. They exclude full third-party page content,
editorial narrative, and unrelated personal/contact information.

The source fixture test compares the public runner's extracted canonical choices
against `reviewed-decisions.yaml`, the six sources' facts
from the independently reviewed October 4 general-election ledger at commit
`af033cb6eff162a7f6becd01177962ae74795ce0` (path
`data/releases/wa-2026-general/source-decisions.yaml`). Keep these expected facts
and the HTML fixtures together: later production ledger refreshes describe later
publications and must not change the expected output of these dated inputs. A
new fixture observation needs its own independently reviewed expected facts.
Index tests
use authored article bodies and a controlled HTTP boundary. These fixtures are
parser exercises; they do not establish live access or approve an automatic baseline.

WFP's October 19 fixture expands to all 17 reviewed Washington rows and the ten
already approved in-inventory mappings. Its expected facts also use the October 19
independent complete-publication review; this is a scoped extension of the five
initial-page facts above. Seven exact rows remain excluded outside the frozen
inventory. The main fixture mirrors the actual response's newline/tab separation
between adjacent `td` cells and leading office whitespace; the alternate layout
minifies the same authored rows. `-initial-page.html` preserves the earlier five
mapped facts to catch accidental fallback to the unchanged discovery page. None
of these snippets reproduces the private original markup.
