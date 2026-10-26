// Sole device-memory capability: one election-specific precinct code, no other state.
const ELECTION = 'wa-2026-general';
const KEY = `seg-precinct-v1:${ELECTION}`;
/** @param {string} electionId @returns {string|null} */
export function loadPrecinct(electionId) {
  if (electionId !== ELECTION) return null;
  try {
    return window.localStorage.getItem(KEY);
  } catch {
    return null;
  }
}
/** @param {string} electionId @param {string} code */
export function savePrecinct(electionId, code) {
  if (electionId !== ELECTION || !/^\d+$/.test(code)) return false;
  try {
    window.localStorage.setItem(KEY, code);
    return true;
  } catch {
    return false;
  }
}
/** @param {string} electionId */
export function clearPrecinct(electionId) {
  if (electionId !== ELECTION) return false;
  try {
    window.localStorage.removeItem(KEY);
    return true;
  } catch {
    return false;
  }
}
