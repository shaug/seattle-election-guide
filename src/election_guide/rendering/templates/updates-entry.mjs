import { wireShellShare } from './share-link.mjs';
import { wireUpdates } from './updates-client.mjs';

export function boot() {
  wireShellShare();
  wireElectionDay();
  wireUpdates();
}

import { wireElectionDay } from './election-day.mjs';
