// Sole device-memory capability: one election-specific precinct code, no other state.
const ELECTIONS = new Set(['wa-2026-general', 'wa-2026-primary']);
/** @param {string} electionId */
const key = (electionId) => `seg-precinct-v1:${electionId}`;
/** @param {string} electionId @param {ReadonlySet<string>} [allowedCodes] @returns {string|null} */
export function loadPrecinct(electionId, allowedCodes) {
  if (!ELECTIONS.has(electionId)) return null;
  try {
    const value = window.localStorage.getItem(key(electionId));
    return electionId === 'wa-2026-primary' && (!value || !allowedCodes?.has(value)) ? null : value;
  } catch {
    return null;
  }
}
/** @param {string} electionId @param {string} code @param {ReadonlySet<string>} [allowedCodes] */
export function savePrecinct(electionId, code, allowedCodes) {
  if (
    !ELECTIONS.has(electionId) ||
    !code ||
    code.length > 100 ||
    [...code].some((character) => character.charCodeAt(0) < 32 || character.charCodeAt(0) === 127)
  )
    return false;
  if (electionId === 'wa-2026-general' && !/^\d+$/.test(code)) return false;
  if (electionId === 'wa-2026-primary' && !allowedCodes?.has(code)) return false;
  try {
    window.localStorage.setItem(key(electionId), code);
    return true;
  } catch {
    return false;
  }
}
/** @param {string} electionId */
export function clearPrecinct(electionId) {
  if (!ELECTIONS.has(electionId)) return false;
  try {
    window.localStorage.removeItem(key(electionId));
    return true;
  } catch {
    return false;
  }
}
