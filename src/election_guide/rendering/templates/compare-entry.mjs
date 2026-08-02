// The Comparisons page's client entry (docs/FRONTEND.md § Modules). Its import
// graph is the whole of the page's client code; the bundle esbuild builds from
// it is inlined into compare.html.j2, which does nothing but invoke `boot`.
import { wireComparisons } from './compare-client.mjs';
import { wireElectionDay } from './election-day.mjs';
import { wireShellShare } from './share-link.mjs';

/** Wire the Comparisons page. */
export function boot() {
  wireComparisons();
  wireElectionDay();
  wireShellShare();
}
