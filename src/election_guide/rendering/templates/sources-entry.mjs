// The standalone sources editor's client entry (docs/FRONTEND.md § Modules).
// No scoring engine reaches this page: it only ever reads and writes a
// selection through the shared fragment codec.
import { requireClientPayload } from './client-payload.mjs';
import { wireElectionDay } from './election-day.mjs';
import { decodeLensFragment, encodeLensFragment, lensContext } from './lens-url.mjs';
import { wireShellShare } from './share-link.mjs';

/**
 * The page's remaining migration debt: its glue is still inline in
 * sources.html.j2 and calls these by name. Issue #239 moves the glue into
 * modules and this object goes with it (see guide-entry.mjs).
 */
export const glue = { decodeLensFragment, encodeLensFragment, lensContext };

/** Wire the sources page's shell behavior and admit its payload, exactly as
 * the guide's entry does. */
export function boot() {
  wireShellShare();
  wireElectionDay();
  return requireClientPayload(document);
}
