// Client-only declarations: names the browser code needs that no published
// payload carries, so nothing here duplicates a Python-origin value
// (docs/FRONTEND.md, The data contract and Shared names). Everything the
// payload does carry is generated into `client-payload.d.ts`; anything added
// here that a Pydantic model could describe belongs there instead.
//
// Ambient on purpose, like the generated declarations beside it: these names
// are read from JSDoc annotations across the module graph.

/**
 * A prior panel's published contract, used only to explain what changed when
 * migrating a stale link (lens-migrate.mjs). Nothing requires it to migrate
 * correctly, so it is narrowed to the fields the report reads — derived from
 * the generated contract rather than restated, so a model change reaches it.
 */
type PanelSnapshot = {
  panel_id: PersonalizationContract['panel_id'];
  categories: Pick<PersonalizationCategory, 'code' | 'member_source_codes'>[];
  sources: Pick<PersonalizationSource, 'code'>[];
};

/** What `shareOrCopyLink` reports back to a caller's status line. */
type ShareResult = 'shared' | 'cancelled' | 'copied' | 'failed';
