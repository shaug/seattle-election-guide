// One race page's client entry (docs/FRONTEND.md § Modules). esbuild bundles
// this import graph and race.html.j2 inlines the result.
import { requireClientPayload } from './client-payload.mjs';
import { wireElectionDay } from './election-day.mjs';
import { wireMeterContext } from './meter-context.mjs';
import { wireMeterTooltips } from './meter-tooltip.mjs';
import { wireRacePage } from './race-client.mjs';
import { wireShellShare } from './share-link.mjs';

/**
 * Wire one race page.
 *
 * The same order the guide boots in, for the same reason: the shell depends on
 * nothing the payload carries, so a page whose payload cannot be read still
 * shares — and on a race page that Share action is the one that copies the
 * race's own canonical address (docs/DESIGN.md § Site shell: the masthead
 * carries the actions on the page) — and its headline meter still opens its
 * per-block tooltips, and its chips are already live: the candidate-context
 * treatment they trigger (docs/METER_V2.md; #315) is a presentation state
 * with no payload of its own, so it needs nothing the admission below hands
 * back. Then the payload is admitted, which either hands back the contract
 * the rest of the page reads or stops the page here, on the complete audited
 * baseline the server rendered.
 */
export function boot() {
  wireShellShare();
  wireElectionDay();
  wireMeterTooltips();
  wireMeterContext();
  wireRacePage(/** @type {RacePayload} */ (requireClientPayload(document)));
}
