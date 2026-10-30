// The guide's Ballot / View / Races controls.
//
// Extracted from guide.html.j2's classic script by issue #239. Two things
// changed in the move, both required by docs/FRONTEND.md:
//
//   * The scope label in the status line comes from the payload's
//     `filter_scopes` rather than from `select.selectedOptions[0].textContent`,
//     and so does the set of tokens the select will accept (The data contract:
//     the DOM is write-only projection). This was the boundary issue #236 left
//     for this ticket.
//   * The control state is read from and written to a query string this module
//     is handed and hands back; `lens-route.mjs` is what touches `location`
//     (§ State and URLs).

import { availableBallotScopes, makeBallotScopeProjector } from './ballot-scopes.mjs';
import { projectCompactFilters } from './compact-filters.mjs';
import { filterStatusParts } from './guide-format.mjs';
import { readContestedOnly, withContestedOnly } from './precinct-ballot.mjs';

/**
 * @typedef {object} ControlState
 * @property {string} scope The Ballot filter token, `'all'` for no filter.
 * @property {'full'|'compact'} view
 * @property {'complete'|'contested'} raceSet
 */

/**
 * The control state one query string names, with every unrecognized or absent
 * value resolved to its default.
 *
 * @param {string} search A query string, `?` included or not.
 * @param {ReadonlySet<string>} knownScopes
 * @param {boolean} [defaultContested]
 * @returns {ControlState}
 */
export function readControlState(search, knownScopes, defaultContested = false) {
  const query = new URLSearchParams(search);
  const requestedScope = query.get('filter');
  return {
    scope: requestedScope && knownScopes.has(requestedScope) ? requestedScope : 'all',
    view: query.get('view') === 'compact' ? 'compact' : 'full',
    raceSet: (
      defaultContested
        ? readContestedOnly(search, true)
        : query.get('races') === 'contested'
    )
      ? 'contested'
      : 'complete',
  };
}

/**
 * The same query string with the control parameters rewritten.
 *
 * Every default is written as absence, so the audited address of the guide
 * carries no control parameters at all. Parameters this page does not own are
 * preserved.
 *
 * @param {string} search
 * @param {ControlState} state
 * @param {boolean} [defaultContested]
 * @returns {string} A query string including its leading `?`, or `''`.
 */
export function writeControlState(search, state, defaultContested = false) {
  const query = new URLSearchParams(search);
  if (state.scope === 'all') query.delete('filter');
  else query.set('filter', state.scope);
  if (state.view === 'compact') query.set('view', 'compact');
  else query.delete('view');
  return withContestedOnly(query.toString(), state.raceSet === 'contested', defaultContested);
}

/**
 * @typedef {object} GuideFilters
 * @property {(options?: { syncUrl?: boolean }) => void} apply Re-apply the
 *   controls' current state to the page.
 * @property {() => void} syncFromUrl Reload the controls from the address bar.
 * @property {(ids:Set<string>|null, reset:boolean) => void} setPrecinct
 * @property {() => void} showEveryRace Clear the filter so a linked race is
 *   reachable, and apply it.
 */

/**
 * Wire the guide's filter controls.
 *
 * @param {GuidePayload} payload
 * @param {import('./lens-route.mjs').LensRouter} router
 * @param {() => void} [onApply]
 * @returns {GuideFilters}
 */
export function wireGuideFilters(payload, router, onApply = () => {}) {
  const select = /** @type {HTMLSelectElement} */ (document.querySelector('#race-filter'));
  const completeFilter = /** @type {HTMLInputElement} */ (
    document.querySelector('#complete-filter')
  );
  const viewInputs = /** @type {HTMLInputElement[]} */ ([
    ...document.querySelectorAll('input[name="ballot-view"]'),
  ]);
  const raceSetInputs = /** @type {HTMLInputElement[]} */ ([
    ...document.querySelectorAll('input[name="race-set"]'),
  ]);
  const status = /** @type {HTMLElement} */ (document.querySelector('#filter-status'));
  const cards = /** @type {HTMLElement[]} */ ([
    ...document.querySelectorAll('[data-publication-race-id]'),
  ]);
  const sections = /** @type {HTMLElement[]} */ ([
    ...document.querySelectorAll('[data-filter-section]'),
  ]);

  const defaultContested = payload.precinct_ballot?.election_id === 'wa-2026-general';
  let precinctIds = /** @type {Set<string>|null} */ (null);
  const scopeLabels = new Map(payload.filter_scopes.map((scope) => [scope.value, scope.label]));
  let knownScopes = new Set(scopeLabels.keys());
  const projectScopes = makeBallotScopeProjector(select);

  /** @returns {ControlState} */
  const controlState = () => ({
    scope: select.value,
    view: viewInputs.find((input) => input.checked)?.value === 'compact' ? 'compact' : 'full',
    raceSet:
      raceSetInputs.find((input) => input.checked)?.value === 'contested'
        ? 'contested'
        : 'complete',
  });

  const syncFromUrl = () => {
    const state = readControlState(router.controlSearch(), knownScopes, defaultContested);
    select.value = state.scope;
    viewInputs.forEach((input) => {
      input.checked = input.value === state.view;
    });
    raceSetInputs.forEach((input) => {
      input.checked = input.value === state.raceSet;
    });
  };

  /** @param {{ syncUrl?: boolean }} [options] */
  const apply = ({ syncUrl = true } = {}) => {
    if (!knownScopes.has(select.value)) select.value = 'all';
    const state = controlState();
    const contestedOnly = state.raceSet === 'contested';
    const compact = state.view === 'compact';
    let visible = 0;
    document.documentElement.classList.toggle('compact-ballot-mode', compact);
    document.documentElement.dataset.ballotView = compact ? 'compact' : 'full';
    cards.forEach((card) => {
      const matchesScope =
        state.scope === 'all' ||
        JSON.parse(/** @type {string} */ (card.dataset.filterTokens)).includes(state.scope);
      const matchesContest = !contestedOnly || card.dataset.contested === 'true';
      const matches =
        matchesScope &&
        (precinctIds === null || precinctIds.has(card.dataset.publicationRaceId ?? '')) &&
        matchesContest;
      card.hidden = !matches;
      if (matches) visible += 1;
    });
    sections.forEach((section) => {
      section.hidden = ![...section.querySelectorAll('[data-publication-race-id]')].some(
        (card) => !(/** @type {HTMLElement} */ (card).hidden),
      );
    });
    const statusParts = filterStatusParts({
      visible,
      contestedOnly,
      compact,
      // The payload names every scope the select offers, so a resolved value
      // always has a label; the fallback covers only a `select.value` the
      // payload does not know, which the markup cannot produce.
      scopeLabel:
        precinctIds !== null
          ? `Selected precinct · ${scopeLabels.get(state.scope) ?? 'All Seattle ballot races'}`
          : (scopeLabels.get(state.scope) ?? 'All Seattle ballot races'),
    });
    status.replaceChildren(
      ...statusParts.map((part, index) => {
        const chunk = document.createElement('span');
        chunk.className = index === 0 ? 'filter-status-part' : 'filter-status-part visually-hidden';
        chunk.textContent = index === 0 ? part : ` · ${part}`;
        return chunk;
      }),
    );
    if (syncUrl)
      router.replaceControlSearch(
        writeControlState(router.controlSearch(), state, defaultContested),
      );
    projectCompactFilters({
      scope: state.scope,
      scopeLabel: scopeLabels.get(state.scope) ?? 'All Seattle ballot races',
      view: compact ? 'Compact' : 'Full',
      races: contestedOnly ? 'Contested' : 'All',
    });
    onApply();
  };

  select.addEventListener('change', () => apply());
  for (const input of [...raceSetInputs, ...viewInputs]) {
    input.addEventListener('change', () => apply());
  }
  syncFromUrl();
  apply({ syncUrl: false });

  return {
    apply,
    syncFromUrl,
    setPrecinct(ids, reset) {
      precinctIds = ids;
      knownScopes = availableBallotScopes(payload.filter_scopes, ids);
      projectScopes(knownScopes);
      select.disabled = false;
      syncFromUrl();
      const search = router.controlSearch();
      const normalized = writeControlState(search, controlState(), defaultContested);
      apply({ syncUrl: reset || normalized !== search });
    },
    showEveryRace() {
      select.value = 'all';
      completeFilter.checked = true;
      apply();
    },
  };
}
