// Ballot membership has no section or sort policy and does not inspect endorsements.
/** @typedef {Record<string, string>} BallotProfile */
/** @typedef {'applicable'|'inapplicable'|'unresolved'} Membership */

/** @param {BallotMembershipContract} contract @param {unknown} value
 * @returns {BallotProfile} */
export function admitProfile(contract, value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
  const input = /** @type {Record<string,unknown>} */ (value);
  /** @type {BallotProfile} */
  const profile = {};
  for (const group of contract.groups) {
    const choice = input[group.id];
    const known =
      group.mode === 'membership'
        ? choice === 'yes' || choice === 'no'
        : choice === 'other' || group.options.some((option) => option.id === choice);
    if (known && typeof choice === 'string') profile[group.id] = choice;
  }
  return profile;
}

/** @param {BallotMembershipContract} contract @param {unknown} input */
export function resolveBallot(contract, input) {
  const profile = admitProfile(contract, input);
  const groups = new Map(contract.groups.map((group) => [group.id, group]));
  /** @type {Record<string, Membership>} */
  const membership = {};
  for (const [id, rule] of Object.entries(contract.races)) {
    if (rule.outside_target) {
      membership[id] = 'inapplicable';
      continue;
    }
    if (rule.shared) {
      membership[id] = 'applicable';
      continue;
    }
    const group = rule.group_id ? groups.get(rule.group_id) : undefined;
    const choice = group ? profile[group.id] : undefined;
    membership[id] =
      !group || !choice || choice === 'other'
        ? 'unresolved'
        : (group.mode === 'membership' ? choice === 'yes' : choice === rule.jurisdiction_id)
          ? 'applicable'
          : 'inapplicable';
  }
  return {
    membership,
    complete:
      contract.groups.every((group) => profile[group.id] && profile[group.id] !== 'other') &&
      !Object.values(membership).includes('unresolved'),
  };
}
