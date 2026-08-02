// The standalone sources editor's client entry (docs/FRONTEND.md § Modules).
// No scoring engine reaches this page: it only ever reads and writes a
// selection through the shared fragment codec.
import { requireClientPayload } from './client-payload.mjs';
import { wireElectionDay } from './election-day.mjs';
import { wireShellShare } from './share-link.mjs';
import { wireSourcesEditor } from './sources-client.mjs';

/** Wire the sources editor, exactly as the guide's entry wires the guide. */
export function boot() {
  wireShellShare();
  wireElectionDay();
  wireSourcesEditor(/** @type {SourcesPayload} */ (requireClientPayload(document)));
}
