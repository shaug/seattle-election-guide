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
