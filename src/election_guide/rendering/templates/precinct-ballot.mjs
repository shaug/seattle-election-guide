// One reviewed voting precinct resolves covered contests independently of sources.
/** @param {PrecinctBallotContract} contract @param {string|null} code */
export function resolvePrecinct(contract, code) {
  const area = contract.precincts.find((p) => p.code === code);
  return {
    status: area ? 'selected' : code === null ? 'all' : 'invalid',
    code: area?.code ?? null,
    contestIds: area ? new Set(area.contest_ids) : null,
  };
}
/** @param {string} search @param {PrecinctBallotContract} contract */
export function readPrecinctSelection(search, contract) {
  const values = new URLSearchParams(search).getAll('precinct');
  if (values.length === 0) return { status: 'absent', code: null };
  if (values.length !== 1) return { status: 'invalid', code: null };
  if (values[0] === 'all') return { status: 'all', code: null };
  const result = resolvePrecinct(contract, values[0]);
  return { status: result.status, code: result.code };
}
/** @param {string} search @param {string|null} code */
export function withPrecinct(search, code) {
  const query = new URLSearchParams(search);
  query.set('precinct', code ?? 'all');
  return `?${query}`;
}

/** Carry only the ballot-selection namespace through a source-selection round trip.
 * Invalid/duplicate values stay explicit, so device memory cannot override them.
 * @param {string} search
 * @param {boolean} [includeRaceMode]
 * @param {boolean} [includePrecinct]
 */
export function ballotQuery(search, includeRaceMode = true, includePrecinct = true) {
  const query = new URLSearchParams();
  const incoming = new URLSearchParams(search);
  for (const key of [
    ...(includePrecinct ? ['precinct'] : []),
    ...(includeRaceMode ? ['races'] : []),
  ]) {
    for (const value of incoming.getAll(key)) query.append(key, value);
  }
  return query.size ? `?${query}` : '';
}

/** @param {string} search @param {boolean} [defaultContested] */
export function readContestedOnly(search, defaultContested = false) {
  const values = new URLSearchParams(search).getAll('races');
  if (values.length !== 1) return defaultContested;
  if (values[0] === 'all') return false;
  if (values[0] === 'contested') return true;
  return defaultContested;
}
/** @param {string} search @param {boolean} contested @param {boolean} [defaultContested] */
export function withContestedOnly(search, contested, defaultContested = false) {
  const query = new URLSearchParams(search);
  if (contested === defaultContested) query.delete('races');
  else query.set('races', contested ? 'contested' : 'all');
  return query.size ? `?${query}` : '';
}

/** Historical selection requires its explicit reviewed supplement; no address context is inherited.
 * @param {PrecinctBallotContract|null|undefined} contract
 */
export function supportedPrecinctContract(contract) {
  if (contract?.election_id === 'wa-2026-general') return true;
  const supplement = contract?.supplement;
  return (
    contract?.election_id === 'wa-2026-primary' &&
    contract.schema_version === '1.0' &&
    supplement?.schema_version === '1.0' &&
    supplement?.election_id === contract.election_id &&
    supplement.mapping_hash === contract.mapping_hash &&
    /^[a-f0-9]{64}$/.test(contract.mapping_hash) &&
    /^[a-f0-9]{40}$/.test(supplement.source_git_commit) &&
    /^[a-f0-9]{64}$/.test(supplement.artifact_sha256) &&
    contract.address_lookup === null
  );
}
