# Preliminary adapter fixtures

These are **historical Nov3 evening schema fixtures**, not current counts, certification,
whole-inventory coverage approval or a production preliminary admission.

`wa-2026-general-historical-county.json` is a JSON field/contest excerpt of the original
County capture SHA256 `eba2d525d864dc57a546b6552c8dffa629746a65351b7002b18b0819c115f68f`.
It retains original election metadata, jurisdiction id/name/shortName and selected complete
contest objects. No selected object's counts or clocks were changed. Its serialization is
derived, not the original byte stream. CD9's empty crossCounties is deliberately retained:
it does not establish whole-contest coverage for a County source.

`wa-2026-general-historical-state.json` excerpts original Media Export SHA256
`3de8a3aba113b76f933774e4b6f2de8319f370b329951ed0b8ca1242b62d4b8e`, retaining election
metadata, the results object with three complete original contest objects, and an empty
localResults list. The statewide root is distinct from County localResults. Export createdAt
is preserved as generation time; it does not prove publisher count-as-of. Source originals
and immutable manifests remain in their original official evidence store.

Synthetic localResults traps and invalid counters in tests are explicit counterexamples,
not edits to these historical fixtures or official factual claims. No live requests occur.
