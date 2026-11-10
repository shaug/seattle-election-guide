# Preliminary update timestamp presentation (#728)

[Issue #728](https://github.com/shaug/seattle-election-guide/issues/728) approves moving the
three retained source-check times from headlines to bodies, expressed as a US date and
12-hour Pacific clock at minute precision. Seconds are omitted without rounding.

`presentation.json` binds each exact previous entry from the unchanged
[#718 classification](../updates-718/classification.json) by SHA-256 to its approved
headline and body. `tests/test_updates_history.py` checks the immutable source audit hash,
the exact three transformations, and equality of every remaining authored field. Negative
cases reject changes to the binding or to dates, slugs, aliases, topics, actions and evidence.

The check instant comes from the original headline's Pacific date/time, independently
corroborated by its unchanged second-precision slug. It is not the publisher count/export
time or a new check. Both permanent aliases and all result/evidence inputs remain unchanged.
Future generated entries use the same body presentation and retain precise slug identity.
