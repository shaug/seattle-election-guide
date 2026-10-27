// Compact precinct slot: the modal edits a draft; only Select changes membership.
import { html, nothing, render } from 'lit-html';
import {
  ballotQuery,
  readPrecinctSelection,
  resolvePrecinct,
  withPrecinct,
} from './precinct-ballot.mjs';
import { clearPrecinct, loadPrecinct, savePrecinct } from './precinct-selection-store.mjs';

const SELECT_LABEL = 'Select';

/** @param {PrecinctBallotContract|null|undefined} contract
 * @param {{controlSearch:()=>string,replaceControlSearch:(search:string)=>void,onHistoryChange:(fn:()=>void)=>void}} router
 * @param {(ids:Set<string>|null, reset:boolean)=>void} onSelection */
export function wirePrecinctControl(contract, router, onSelection) {
  const root = document.querySelector('[data-precinct-control]');
  if (!contract || contract.election_id !== 'wa-2026-general' || !root) return;
  const endorsementsPath = contract.endorsements_path;
  const comparisonsPath = contract.comparisons_path;
  if (!endorsementsPath || !comparisonsPath) return;
  const dialog = root.querySelector('dialog');
  const form = root.querySelector('form');
  const fields = /** @type {HTMLElement|null} */ (root.querySelector('[data-precinct-fields]'));
  const summary = /** @type {HTMLElement|null} */ (root.querySelector('[data-precinct-summary]'));
  const status = /** @type {HTMLElement|null} */ (root.querySelector('[data-precinct-status]'));
  const appliedNotice = /** @type {HTMLElement|null} */ (
    root.querySelector('[data-precinct-applied-notice]')
  );
  const submit = /** @type {HTMLButtonElement|null} */ (
    root.querySelector('[data-precinct-submit]')
  );
  const cancel = root.querySelector('[data-precinct-cancel]');
  if (!dialog || !form || !fields || !summary || !status || !appliedNotice || !submit || !cancel)
    return;
  submit.textContent = SELECT_LABEL;
  let code = /** @type {string|null} */ (null);
  let draft = /** @type {string|null} */ (null);
  let storageWarning = '';
  const restoreFocus = () =>
    /** @type {HTMLElement|null} */ (summary.querySelector('button'))?.focus();
  const open = () => {
    draft = code;
    const area = contract.precincts.find((p) => p.code === code);
    const input = /** @type {HTMLInputElement} */ (fields.querySelector('input'));
    input.value = area?.name ?? '';
    submit.disabled = draft === null;
    render(nothing, status);
    restoreFocus();
    dialog.showModal();
    input.focus();
  };
  const update = (reset = false) => {
    const selection = readPrecinctSelection(router.controlSearch(), contract);
    code = selection.code;
    const area = contract.precincts.find((p) => p.code === code);
    render(
      html`<button class="precinct-open${area ? ' precinct-selected' : ''}" type="button" data-precinct-open aria-haspopup="dialog" aria-controls="precinct-dialog" @click=${open}>${area?.name ?? SELECT_LABEL}</button>${area ? html`<button class="precinct-clear" type="button" data-precinct-clear aria-label="Clear precinct selection" @click=${() => choose(null)}>×</button>` : nothing}`,
      summary,
    );
    const appliedWarning =
      selection.status === 'invalid'
        ? 'Precinct not recognized. Showing ordinary browsing.'
        : storageWarning;
    render(html`${appliedWarning}`, appliedNotice);
    appliedNotice.hidden = appliedWarning === '';
    render(nothing, status);
    const input = /** @type {HTMLInputElement} */ (fields.querySelector('input'));
    input.value = area?.name ?? '';
    onSelection(resolvePrecinct(contract, code).contestIds, reset || Boolean(area));
    refreshPrecinctLinks(contract, router.controlSearch());
  };
  /** @param {string|null} next */
  const choose = (next) => {
    const remembered =
      next === null
        ? clearPrecinct(contract.election_id)
        : savePrecinct(contract.election_id, next);
    storageWarning = remembered
      ? ''
      : 'This device could not remember the choice; the link still works.';
    router.replaceControlSearch(withPrecinct(router.controlSearch(), next));
    update(true);
    if (dialog.open) dialog.close();
    restoreFocus();
  };
  /** @param {Event} event */
  const edit = (event) => {
    const value = /** @type {HTMLInputElement} */ (event.target).value.trim().toUpperCase();
    draft =
      contract.precincts.find((p) => p.code === value || p.name.toUpperCase() === value)?.code ??
      null;
    submit.disabled = draft === null;
    render(html`${value && draft === null ? 'Choose a listed precinct.' : ''}`, status);
  };
  render(
    html`<div class="filter-select-control">
      <label class="filter-control-label" for="voting-precinct">Search precincts</label>
      <input class="filter-select" id="voting-precinct" list="voting-precinct-options" autocomplete="off" @input=${edit} @change=${edit}>
      <datalist id="voting-precinct-options">${contract.precincts.map((p) => html`<option value=${p.name}>${p.code}</option>`)}</datalist>
    </div>`,
    fields,
  );
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    if (draft !== null) choose(draft);
  });
  cancel.addEventListener('click', () => dialog.close());
  dialog.addEventListener('keydown', (event) => {
    if (event.key !== 'Tab') return;
    const targets = /** @type {HTMLElement[]} */ ([
      ...dialog.querySelectorAll('input, a[href], button:not(:disabled)'),
    ]);
    const first = targets[0];
    const last = targets.at(-1);
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last?.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first?.focus();
    }
  });
  dialog.addEventListener('close', restoreFocus);
  root.removeAttribute('hidden');
  const initial = readPrecinctSelection(router.controlSearch(), contract);
  if (initial.status === 'absent') {
    const remembered = resolvePrecinct(contract, loadPrecinct(contract.election_id)).code;
    router.replaceControlSearch(withPrecinct(router.controlSearch(), remembered));
  }
  update();
  router.onHistoryChange(() => {
    storageWarning = '';
    update();
    if (dialog.open) dialog.close();
  });
}

/** Project complete renderer-owned routes with the current ballot context.
 * @param {PrecinctBallotContract|null|undefined} contract @param {string} search */
export function refreshPrecinctLinks(contract, search) {
  if (contract?.election_id !== 'wa-2026-general') return;
  const destinations = {
    endorsements: contract.endorsements_path,
    comparisons: contract.comparisons_path,
    sources: contract.sources_path,
  };
  const selection = readPrecinctSelection(search, contract);
  for (const link of /** @type {NodeListOf<HTMLAnchorElement>} */ (
    document.querySelectorAll('[data-precinct-link]')
  )) {
    const key = /** @type {keyof typeof destinations} */ (link.dataset.precinctLink);
    const target = destinations[key];
    if (!target) continue;
    const query =
      key === 'sources' ? ballotQuery(search) : withPrecinct(ballotQuery(search), selection.code);
    link.href = `${target}${query}`;
  }
}
