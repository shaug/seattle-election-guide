// One device store for election-bound ballot profiles. No addresses or source choices.
/** @typedef {{version: 1, mode: 'ballot'|'all', choices: Record<string,string>}} SavedBallot */
/** @param {string} electionId @param {SavedBallot|null} [value]
 * @returns {Promise<unknown>} */
function access(electionId, value) {
  return new Promise((resolve, reject) => {
    const open = indexedDB.open('seg-ballot-profile', 1);
    open.onupgradeneeded = () => open.result.createObjectStore('profiles');
    open.onerror = () => reject(open.error);
    open.onsuccess = () => {
      const db = open.result;
      const transaction = db.transaction(
        'profiles',
        value === undefined ? 'readonly' : 'readwrite',
      );
      const store = transaction.objectStore('profiles');
      const request =
        value === undefined
          ? store.get(electionId)
          : value === null
            ? store.delete(electionId)
            : store.put(value, electionId);
      /** @type {unknown} */
      let result;
      request.onsuccess = () => {
        result = request.result;
      };
      transaction.oncomplete = () => {
        db.close();
        resolve(result);
      };
      transaction.onabort = transaction.onerror = () => {
        db.close();
        reject(transaction.error);
      };
    };
    open.onblocked = () => reject(new Error('Ballot storage unavailable'));
  });
}
/** @param {string} electionId */
export const readBallotProfile = (electionId) => access(electionId);
/** @param {string} electionId @param {SavedBallot|null} value */
export const writeBallotProfile = (electionId, value) => access(electionId, value);
