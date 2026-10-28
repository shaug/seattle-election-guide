// Compact precinct slot: the modal edits a draft; only Select changes membership.
import { html, nothing, render } from 'lit-html';
import {
  ballotQuery,
  readPrecinctSelection,
  resolvePrecinct,
  withPrecinct,
} from './precinct-ballot.mjs';
import { clearPrecinct, loadPrecinct, savePrecinct } from './precinct-selection-store.mjs';
import { createVotingAddressLookup } from './voting-address-lookup.mjs';

const SELECT_LABEL = 'Select';

/** @param {PrecinctBallotContract|null|undefined} contract
 * @param {{controlSearch:()=>string,replaceControlSearch:(search:string)=>void,onHistoryChange:(fn:()=>void)=>void}} router
 * @param {(ids:Set<string>|null, reset:boolean)=>void} onSelection
 * @param {ReturnType<typeof createVotingAddressLookup>} [providedLookup] */
export function wirePrecinctControl(contract, router, onSelection, providedLookup) {
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
  const addressEnabled =
    contract.address_lookup?.election_id === contract.election_id &&
    contract.address_lookup?.mapping_hash === contract.mapping_hash;
  const lookup = addressEnabled
    ? (providedLookup ?? createVotingAddressLookup(contract.address_lookup, contract.precincts))
    : null;
  let addressMode = false;
  let generation = 0;
  let debounce = /** @type {ReturnType<typeof setTimeout>|undefined} */ (undefined);
  let request = /** @type {AbortController|null} */ (null);
  let options = /** @type {any[]} */ ([]);
  let active = -1;
  let resolving = false;
  const directInput = () =>
    /** @type {HTMLInputElement} */ (fields.querySelector('#voting-precinct'));
  const addressInput = () =>
    /** @type {HTMLInputElement|null} */ (fields.querySelector('[data-address-input]'));
  const list = () =>
    /** @type {HTMLElement|null} */ (fields.querySelector('[data-address-options]'));
  const dismissOptions = () => {
    options = [];
    active = -1;
    const target = list();
    if (target) {
      render(nothing, target);
      target.hidden = true;
    }
    addressInput()?.setAttribute('aria-expanded', 'false');
    addressInput()?.removeAttribute('aria-activedescendant');
  };
  const invalidate = () => {
    resolving = false;
    generation += 1;
    clearTimeout(debounce);
    request?.abort();
    request = null;
    dismissOptions();
  };
  const resetAddress = () => {
    invalidate();
    const input = addressInput();
    if (input) input.value = '';
  };
  /** @param {boolean} address */
  const switchMode = (address) => {
    resetAddress();
    addressMode = address;
    draft = null;
    submit.disabled = true;
    const direct = /** @type {HTMLElement|null} */ (fields.querySelector('[data-direct-fields]'));
    const addresses = /** @type {HTMLElement|null} */ (
      fields.querySelector('[data-address-fields]')
    );
    if (direct) direct.hidden = address;
    if (addresses) addresses.hidden = !address;
    fields.querySelector('[data-address-mode]')?.setAttribute('aria-pressed', String(address));
    fields.querySelector('[data-direct-mode]')?.setAttribute('aria-pressed', String(!address));
    render(nothing, status);
    (address ? addressInput() : directInput())?.focus();
  };
  /** @param {{text:string,magicKey:string,isCollection:boolean}} option */
  const selectAddress = async (option) => {
    invalidate();
    const version = generation;
    resolving = true;
    request = new AbortController();
    draft = null;
    submit.disabled = true;
    const input = addressInput();
    if (input) input.value = option.text;
    render(html`Checking the selected canonical address…`, status);
    const result = await lookup?.resolve(option, request.signal);
    if (version !== generation || !dialog.open || !addressMode) return;
    resolving = false;
    const found = contract.precincts.find((p) => p.code === result?.code);
    draft = result?.status === 'resolved' && found ? found.code : null;
    submit.disabled = draft === null;
    render(
      html`${draft ? `Canonical street/building address maps to ${found?.name}. Units and voter registration are not verified. Select to apply.` : 'Address could not be confirmed. Choose your precinct directly or try another address.'}`,
      status,
    );
  };
  const showOptions = () => {
    const target = list();
    if (!target) return;
    render(
      html`${options.map((option, index) => html`<li id=${`address-option-${index}`} role="option" aria-selected=${index === active ? 'true' : 'false'} @pointerdown=${(/** @type {PointerEvent} */ event) => event.preventDefault()} @click=${() => selectAddress(option)}>${option.text}</li>`)}`,
      target,
    );
    target.hidden = options.length === 0;
    addressInput()?.setAttribute('aria-expanded', String(options.length > 0));
    if (active >= 0) {
      addressInput()?.setAttribute('aria-activedescendant', `address-option-${active}`);
      target.querySelector(`#address-option-${active}`)?.scrollIntoView?.({ block: 'nearest' });
    }
  };
  const editAddress = () => {
    invalidate();
    draft = null;
    submit.disabled = true;
    const text = addressInput()?.value ?? '';
    const version = generation;
    render(nothing, status);
    if (text.trim().length < 3 || text.length > 300) return;
    debounce = setTimeout(async () => {
      request = new AbortController();
      render(html`Finding address suggestions…`, status);
      const suggestions = await lookup?.suggest(text, request.signal);
      if (version !== generation || !dialog.open || !addressMode) return;
      options = suggestions ?? [];
      showOptions();
      render(
        html`${options.length ? `${options.length} suggestions. Choose a canonical address; this does not verify a unit or voter registration.` : 'No address suggestions available. Choose your precinct directly or try again.'}`,
        status,
      );
    }, 300);
  };
  /** @param {KeyboardEvent} event */
  const addressKey = (event) => {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      if (!options.length) return;
      event.preventDefault();
      active =
        active < 0
          ? event.key === 'ArrowDown'
            ? 0
            : options.length - 1
          : (active + (event.key === 'ArrowDown' ? 1 : -1) + options.length) % options.length;
      showOptions();
    } else if (event.key === 'Enter' && (options.length || draft === null)) {
      event.preventDefault();
      if (active >= 0) void selectAddress(options[active]);
    } else if (event.key === 'Escape' && options.length) {
      event.preventDefault();
      event.stopPropagation();
      invalidate();
    } else if (event.key === 'Tab') {
      if (resolving) dismissOptions();
      else invalidate();
    }
  };
  const restoreFocus = () =>
    /** @type {HTMLElement|null} */ (summary.querySelector('button'))?.focus();
  const open = () => {
    resetAddress();
    addressMode = false;
    fields.querySelector('[data-address-mode]')?.setAttribute('aria-pressed', 'false');
    fields.querySelector('[data-direct-mode]')?.setAttribute('aria-pressed', 'true');
    draft = code;
    const area = contract.precincts.find((p) => p.code === code);
    const input = /** @type {HTMLInputElement} */ (fields.querySelector('#voting-precinct'));
    input.value = area?.name ?? '';
    submit.disabled = draft === null;
    const direct = /** @type {HTMLElement|null} */ (fields.querySelector('[data-direct-fields]'));
    const address = /** @type {HTMLElement|null} */ (fields.querySelector('[data-address-fields]'));
    if (direct) direct.hidden = false;
    if (address) address.hidden = true;
    render(nothing, status);
    restoreFocus();
    dialog.showModal();
    input.focus();
  };
  const update = (reset = false) => {
    resetAddress();
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
    const input = /** @type {HTMLInputElement} */ (fields.querySelector('#voting-precinct'));
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
    invalidate();
    const value = /** @type {HTMLInputElement} */ (event.target).value.trim().toUpperCase();
    draft =
      contract.precincts.find((p) => p.code === value || p.name.toUpperCase() === value)?.code ??
      null;
    submit.disabled = draft === null;
    render(html`${value && draft === null ? 'Choose a listed precinct.' : ''}`, status);
  };
  render(
    html`${lookup ? html`<div class="address-mode-choice"><button type="button" data-direct-mode aria-pressed="true" @click=${() => switchMode(false)}>Use precinct</button><button type="button" data-address-mode aria-pressed="false" @click=${() => switchMode(true)}>Use voting address</button></div>` : nothing}<div class="filter-select-control" data-direct-fields>
      <label class="filter-control-label" for="voting-precinct">Search precincts</label>
      <input class="filter-select" id="voting-precinct" list="voting-precinct-options" autocomplete="off" @input=${edit} @change=${edit}>
      <datalist id="voting-precinct-options">${contract.precincts.map((p) => html`<option value=${p.name}>${p.code}</option>`)}</datalist>
    </div>${
      lookup
        ? html`<div data-address-fields hidden>
      <label for="voting-address">Voting address</label>
      <input id="voting-address" data-address-input class="filter-select" role="combobox" aria-autocomplete="list" aria-controls="voting-address-options" aria-expanded="false" autocomplete="off" maxlength="300" @input=${editAddress} @keydown=${addressKey}>
      <ul id="voting-address-options" data-address-options role="listbox" aria-label="Matching canonical addresses" hidden></ul>
      <p class="address-privacy">Typed text goes to King County GIS; selected address and coordinates go to county-maintained Esri services. Providers may retain requests. SEG remembers only your precinct.</p>
    </div>`
        : nothing
    }`,
    fields,
  );
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    if (draft !== null) choose(draft);
  });
  const discardDraft = () => {
    resetAddress();
    draft = null;
    submit.disabled = true;
  };
  cancel.addEventListener('click', () => {
    discardDraft();
    dialog.close();
    restoreFocus();
  });
  dialog.addEventListener('cancel', discardDraft);
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
  dialog.addEventListener('close', () => {
    // Native close events are queued: an already reopened session owns its state.
    if (dialog.open) return;
    resetAddress();
    draft = null;
    submit.disabled = true;
    restoreFocus();
  });
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
