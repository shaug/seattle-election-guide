// The endorsements guide's client entry (docs/FRONTEND.md § Modules). esbuild
// bundles this import graph and guide.html.j2 inlines the result.
import { wireElectionDay } from './election-day.mjs';
import { compareRaceResults } from './lens-divergence.mjs';
import { migrateLensState } from './lens-migrate.mjs';
import { Rational, scoreSelection } from './lens-score.mjs';
import { decodeLensFragment, encodeLensFragment, lensContext } from './lens-url.mjs';
import { wireShellShare } from './share-link.mjs';

/**
 * The guide's remaining migration debt, not the pattern to copy: several
 * hundred lines of glue still live in the template's `<script type="module">`
 * and call these by name, so the entry hands them over in one object the
 * template destructures. Issue #239 moves that glue into modules and takes
 * this object with it, leaving `boot` as the entry's whole surface.
 *
 * An object rather than re-exports: two modules exporting one name reads, to
 * the shared purity guard, as the module that owns the name borrowing it from
 * the one that re-exports it.
 */
export const glue = {
  Rational,
  compareRaceResults,
  decodeLensFragment,
  encodeLensFragment,
  lensContext,
  migrateLensState,
  scoreSelection,
};

/** Wire the guide's shell behavior. */
export function boot() {
  wireShellShare();
  wireElectionDay();
}
