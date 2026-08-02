// The client entry for the site-shell documents: the guide archive index and
// the About page (docs/FRONTEND.md § Modules — each page has one client entry).
// Those pages carry no page-specific behavior of their own, only the masthead
// Share action every shell shares, so one entry serves them all.
import { wireShellShare } from './share-link.mjs';

/** Wire the shell behavior every full document carries. */
export function boot() {
  wireShellShare();
}
