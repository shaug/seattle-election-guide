// The embedded JSON payload's shape, as the client consumes it
// (docs/FRONTEND.md § The data contract).
//
// HAND-WRITTEN, AND DELIBERATELY TEMPORARY. The document's rule is that the
// publication view model emits JSON Schema and the build generates these
// declarations from it, so a Python model change that breaks a client consumer
// fails `make check`. Issue #236 does that; until it lands, nothing connects
// these names to `publication/personalization.py` and `publication/
// comparisons.py` except review. Transcribed from those models rather than
// from the client's usage, so the gap is a stale copy rather than a guess —
// but it is still a copy, and #236 replaces this whole file with generated
// output.
//
// Scope is what client modules actually read. The Pydantic models carry more
// (panel_version, section ordering, policy toggles); adding a field here that
// no module consumes would be inventing contract the generator will overwrite.
//
// Ambient on purpose: these names are read from a dozen JSDoc annotations
// across the module graph, and `import('./client-payload.js').Personalization`
// at every use site buys nothing when the payload is a single global contract.

/** A cell's published stance for one source in one race. */
type LensCellState =
  | 'endorsement'
  | 'multi_endorsement'
  | 'no_endorsement'
  | 'not_covered'
  | 'unavailable'
  | 'unverified';

/** The audited letter grades, in published order. */
type LensGrade = 'A+' | 'A' | 'B' | 'C' | 'D';

/** A grade a personalized score can resolve to, including the two non-letter outcomes. */
type ScoreGrade = LensGrade | 'TIED' | 'Insufficient';

interface PersonalizationPolicy {
  comparison_source_codes: string[];
  maximum_url_characters: number;
}

interface PersonalizationGrade {
  grade: LensGrade;
  /** An exact rational in `numerator/denominator` (or integer) form. */
  minimum_share: string;
  minimum_explicit_sources: number | null;
}

interface PersonalizationScoring {
  configuration_id: string;
  minimum_explicit_sources: number;
  grades: PersonalizationGrade[];
}

interface PersonalizationCategory {
  code: string;
  label: string;
  selectable: boolean;
  panel_role: 'tallying' | 'comparison';
  member_source_codes: string[];
}

interface PersonalizationSource {
  code: string;
  selectable: boolean;
  panel_role: 'consensus' | 'comparison';
}

interface PersonalizationCell {
  source_code: string;
  state: LensCellState;
  /** Candidate id to an exact rational share of this source's support. */
  allocation: Record<string, string>;
  confidence_warning: boolean;
}

interface PersonalizationRace {
  race_id: string;
  eligible_source_codes: string[];
  cells: PersonalizationCell[];
  candidate_order: string[];
}

interface PersonalizationRetiredCode {
  kind: 'source' | 'category';
  code: string;
  former_id: string;
  reason: string;
}

/** The published personalization contract: the panel, its scoring, and its races. */
interface Personalization {
  panel_id: string;
  panel_hash: string;
  policy: PersonalizationPolicy;
  scoring: PersonalizationScoring;
  categories: PersonalizationCategory[];
  sources: PersonalizationSource[];
  retired_codes: PersonalizationRetiredCode[];
  races: PersonalizationRace[];
}

/**
 * A prior panel's published contract, used only to explain what changed when
 * migrating a stale link (lens-migrate.mjs). Nothing requires it to migrate
 * correctly, so only the fields the report reads are declared.
 */
interface PanelSnapshot {
  panel_id: string;
  categories: Pick<PersonalizationCategory, 'code' | 'member_source_codes'>[];
  sources: Pick<PersonalizationSource, 'code'>[];
}

interface ComparisonBaseline {
  leading_pick_ids: string[];
  /** An exact rational, or null when no source published an endorsement. */
  share: string | null;
  explicit_source_count: number;
}

interface ComparisonDisplayRace {
  race_id: string;
  race_label: string;
  section_id: string;
  section_label: string;
  candidate_names: Record<string, string>;
  measure_response_labels: Record<string, string>;
  baseline: ComparisonBaseline;
}

/** The published comparison display contract: the all-sources result per race. */
interface Comparisons {
  display_index: ComparisonDisplayRace[];
}

/** The `[data-comparison-bindings]` payload the Comparisons page embeds. */
interface ComparePageBindings {
  data_version: string;
  default_columns: string[];
  personalization: Personalization;
  comparisons: Comparisons;
  source_labels: Record<string, string>;
  contested_race_ids: string[];
}

interface Window {
  /**
   * share-link.mjs publishes its one share/copy policy here for the guide's
   * race-dialog routing, which predates the module bundle and still runs as a
   * classic script. Optional because only that module assigns it.
   */
  shareOrCopyLink?: (url: string, title: string) => Promise<ShareResult>;
}

/** What `shareOrCopyLink` reports back to a caller's status line. */
type ShareResult = 'shared' | 'cancelled' | 'copied' | 'failed';
