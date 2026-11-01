# Release policy fixtures

`minimal-publication-view-model.json` is synthetic test data for artifact identity,
publication, promotion and receipt contracts. It retains one complete King County
Assessor fixture contest, six synthetic source states, exact allocations,
comparison/personalization contracts and provenance. Each load is independently
parsed and fully validated; callers never share mutable model state.

It was reduced once from the existing rendering fixture. It is not endorsement
verification evidence or a production input. Full real-dataset publication builds,
multi-race hosting and browser contracts continue to use their existing fixtures.

`published-general-67.json` is the exact canonical public publication record from
workflow run `41273507737`, attempt 1, published source
`79ebdd7811599d9073b5eaa5de6097f415aead39` (general release 67). Its SHA-256 is
`74388b410ef1b3893fc70a70c84e329515479f5b02d0e3a73f65718e21ea2b81`. It preserves
the real legacy serialized shape and deployment identity for compatibility tests;
new optional hosting fields must not change that immutable record's canonical bytes.
