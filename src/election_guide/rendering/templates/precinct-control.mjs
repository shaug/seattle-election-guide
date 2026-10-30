// Compact precinct slot: the modal edits a draft; only Select changes membership.
import { html, nothing, render } from 'lit-html';
import { repeat } from 'lit-html/directives/repeat.js';
import { filterIcon } from './compact-filters.mjs';
import {
  ballotQuery,
  readPrecinctSelection,
  resolvePrecinct,
  withPrecinct,
} from './precinct-ballot.mjs';
import { clearPrecinct, loadPrecinct, savePrecinct } from './precinct-selection-store.mjs';
import { createVotingAddressLookup } from './voting-address-lookup.mjs';

const SELECT_LABEL = 'Select';
/** @typedef {{kind:'precinct',text:string,code:string}|{kind:'address',text:string,magicKey:string,isCollection:boolean}} BallotOption */
/** @typedef {{kind:'precinct'|'address',text:string,code:string}} BallotChoice */
/** Render the current session's distinct option objects without changing selection state.
 * @param {BallotOption[]} options @param {number} active
 * @param {(option:BallotOption)=>void} select */
export function ballotOptionsTemplate(options, active, select) {
  // Objects persist within a query; labels and provider keys may be duplicated.
  return html`${repeat(
    options,
    (option) => option,
    (option, index) =>
      html`<li id=${`ballot-option-${index}`} class="ballot-option" role="option" data-kind=${option.kind} data-code=${option.kind === 'precinct' ? option.code : nothing} aria-selected=${index === active ? 'true' : 'false'} @pointerdown=${(/** @type {PointerEvent} */ event) => event.preventDefault()} @click=${() => {
        void select(option);
      }}><span class="ballot-option-text">${option.text}</span><span class="ballot-option-type">${option.kind === 'precinct' ? 'Precinct' : 'Address'}</span></li>`,
  )}`;
}

/** Only reviewed Seattle names with a unique complete district/code may shorten.
 * @param {{name:string}} area @param {ReadonlyArray<{name:string}>} precincts */
export function compactPrecinctName(area, precincts) {
  const match = /^SEA (\d{2}-\d{4})$/.exec(area.name);
  if (!match) return area.name;
  const short = match[1];
  return precincts.filter((p) => p.name === short || p.name === `SEA ${short}`).length === 1
    ? short
    : area.name;
}

/** @param {PrecinctBallotContract|null|undefined} contract
 * @param {{controlSearch:()=>string,replaceControlSearch:(search:string)=>void,onHistoryChange:(fn:()=>void)=>void}} router
 * @param {(ids:Set<string>|null, reset:boolean)=>void} onSelection
 * @param {ReturnType<typeof createVotingAddressLookup>} [providedLookup] */
export function wirePrecinctControl(contract, router, onSelection, providedLookup) {
  const root = document.querySelector('[data-precinct-control]');
  if (contract?.election_id !== 'wa-2026-general' || !root) return;
  if (!contract.endorsements_path || !contract.comparisons_path) return;
  const dialog = root.querySelector('dialog');
  const form = root.querySelector('form');
  const fields = /** @type {HTMLElement|null} */ (root.querySelector('[data-precinct-fields]'));
  const summary = /** @type {HTMLElement|null} */ (root.querySelector('[data-precinct-summary]'));
  const status = /** @type {HTMLElement|null} */ (root.querySelector('[data-precinct-status]'));
  const notice = /** @type {HTMLElement|null} */ (
    root.querySelector('[data-precinct-applied-notice]')
  );
  const submit = /** @type {HTMLButtonElement|null} */ (
    root.querySelector('[data-precinct-submit]')
  );
  const cancel = root.querySelector('[data-precinct-cancel]');
  if (!dialog || !form || !fields || !summary || !status || !notice || !submit || !cancel) return;
  const lookup =
    contract.address_lookup?.election_id === contract.election_id &&
    contract.address_lookup?.mapping_hash === contract.mapping_hash
      ? (providedLookup ?? createVotingAddressLookup(contract.address_lookup, contract.precincts))
      : null;
  let code = /** @type {string|null} */ (null);
  let draft = /** @type {BallotChoice|null} */ (null);
  let storageWarning = '';
  let generation = 0;
  let debounce = /** @type {ReturnType<typeof setTimeout>|undefined} */ (undefined);
  let request = /** @type {AbortController|null} */ (null);
  let options = /** @type {BallotOption[]} */ ([]);
  let active = -1;
  let resolving = false;
  let composing = false;
  const input = () => /** @type {HTMLInputElement} */ (fields.querySelector('#voting-precinct'));
  const list = () => /** @type {HTMLElement} */ (fields.querySelector('[data-ballot-options]'));
  const fitOptions = () => {
    if (!dialog.open) return;
    const actions = form.querySelector('.precinct-actions');
    const bottom = Math.min(
      dialog.getBoundingClientRect().bottom,
      actions?.getBoundingClientRect().top ?? dialog.getBoundingClientRect().bottom,
    );
    const space = bottom - input().getBoundingClientRect().bottom;
    list().style.setProperty('--precinct-options-height', `${Math.max(0, space - 20)}px`);
  };
  const viewport = document.defaultView?.visualViewport;
  const fitViewport = () => {
    if (viewport) {
      dialog.style.setProperty('--precinct-viewport-height', `${viewport.height}px`);
      dialog.style.setProperty('--precinct-viewport-top', `${viewport.offsetTop}px`);
    }
    fitOptions();
  };
  const dismiss = () => {
    options = [];
    active = -1;
    render(nothing, list());
    list().hidden = true;
    input().setAttribute('aria-expanded', 'false');
    input().removeAttribute('aria-activedescendant');
  };
  const invalidate = () => {
    generation += 1;
    clearTimeout(debounce);
    request?.abort();
    request = null;
    resolving = false;
    dismiss();
  };
  const discard = () => {
    invalidate();
    composing = false;
    draft = null;
    input().value = '';
    submit.disabled = true;
    render(nothing, status);
  };
  /** @param {BallotOption} option */
  const select = async (option) => {
    if (!dialog.open || !options.includes(option)) return;
    invalidate();
    const version = generation;
    draft = null;
    submit.disabled = true;
    input().value = option.text;
    if (option.kind === 'precinct') {
      draft = { kind: 'precinct', code: option.code, text: option.text };
      submit.disabled = false;
      render(html`<span class="visually-hidden">Precinct selected: ${option.text}.</span>`, status);
      return;
    }
    resolving = true;
    request = new AbortController();
    render(html`Checking the selected canonical address…`, status);
    let result;
    try {
      result = await lookup?.resolve(option, request.signal);
    } catch {
      result = null;
    }
    if (version !== generation || !dialog.open) return;
    resolving = false;
    const found = contract.precincts.find((p) => p.code === result?.code);
    if (result?.status === 'resolved' && found) {
      draft = { kind: 'address', code: found.code, text: option.text };
      submit.disabled = false;
    }
    render(
      html`${draft ? `Precinct: ${found?.name}` : 'Address could not be confirmed. Choose a precinct suggestion or try another address.'}`,
      status,
    );
  };
  const show = () => {
    render(
      ballotOptionsTemplate(options, active, (option) => {
        void select(option);
      }),
      list(),
    );
    list().hidden = options.length === 0;
    fitOptions();
    input().setAttribute('aria-expanded', String(options.length > 0));
    if (active >= 0) {
      input().setAttribute('aria-activedescendant', `ballot-option-${active}`);
      list().querySelector(`#ballot-option-${active}`)?.scrollIntoView?.({ block: 'nearest' });
    } else input().removeAttribute('aria-activedescendant');
  };
  const edit = () => {
    invalidate();
    draft = null;
    submit.disabled = true;
    if (composing) return;
    const text = input().value.trim();
    const query = text.toUpperCase();
    const version = generation;
    if (!query) {
      render(nothing, status);
      return;
    }
    const matches = contract.precincts.filter(
      (p) => p.code.includes(query) || p.name.toUpperCase().includes(query),
    );
    const exact = matches.filter((p) => p.code === query || p.name.toUpperCase() === query);
    const ordered = [...exact, ...matches.filter((p) => !exact.includes(p))];
    const local = /** @type {BallotOption[]} */ (
      ordered.slice(0, 10).map((p) => ({ kind: 'precinct', text: p.name, code: p.code }))
    );
    options = local;
    show();
    const localStatus = local.length ? 'Precinct suggestions available.' : 'No matching precincts.';
    render(
      html`${lookup && text.length >= 3 ? 'Finding address suggestions…' : localStatus}`,
      status,
    );
    if (!lookup || text.length < 3 || text.length > 300) return;
    debounce = setTimeout(async () => {
      request = new AbortController();
      let suggestions;
      try {
        suggestions = await lookup.suggest(text, request.signal);
      } catch {
        suggestions = [];
      }
      if (version !== generation || !dialog.open) return;
      const selected = options[active];
      options = [
        ...local,
        ...suggestions.map(
          (/** @type {{text:string,magicKey:string,isCollection:boolean}} */ value) =>
            /** @type {BallotOption} */ ({ ...value, kind: 'address' }),
        ),
      ];
      active = selected ? options.indexOf(selected) : -1;
      show();
      render(
        html`${suggestions.length ? 'Suggestions available.' : local.length ? localStatus : 'No suggestions available.'}`,
        status,
      );
    }, 300);
  };
  /** @param {KeyboardEvent} event */
  const key = (event) => {
    if (event.isComposing || composing) return;
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      if (!options.length) return;
      event.preventDefault();
      active =
        active < 0
          ? event.key === 'ArrowDown'
            ? 0
            : options.length - 1
          : (active + (event.key === 'ArrowDown' ? 1 : -1) + options.length) % options.length;
      show();
    } else if (event.key === 'Enter' && (options.length || draft === null)) {
      event.preventDefault();
      if (active >= 0) void select(options[active]);
    } else if (event.key === 'Escape' && options.length) {
      event.preventDefault();
      event.stopPropagation();
      invalidate();
    } else if (event.key === 'Tab') {
      if (resolving) dismiss();
      else invalidate();
    }
  };
  const restoreFocus = () => {
    const opener = /** @type {HTMLElement|null} */ (summary.querySelector('button'));
    opener?.setAttribute('aria-expanded', String(dialog.open));
    opener?.focus();
  };
  const open = () => {
    discard();
    const area = contract.precincts.find((p) => p.code === code);
    if (area)
      draft = {
        code: area.code,
        kind: 'precinct',
        text: area.name,
      };
    input().value = draft?.text ?? '';
    submit.disabled = draft === null;
    restoreFocus();
    fitViewport();
    dialog.showModal();
    summary.querySelector('button')?.setAttribute('aria-expanded', 'true');
    input().focus();
    fitOptions();
  };
  const update = (reset = false) => {
    discard();
    const selection = readPrecinctSelection(router.controlSearch(), contract);
    code = selection.code;
    const area = contract.precincts.find((p) => p.code === code);
    render(
      html`<button class="precinct-open compact-filter-trigger${area ? ' precinct-selected' : ''}" type="button" data-precinct-open aria-label=${`Precinct: ${area?.name ?? SELECT_LABEL}`} title=${`Precinct: ${area?.name ?? SELECT_LABEL}`} aria-haspopup="dialog" aria-controls="precinct-dialog" aria-expanded="false" @click=${open}>${filterIcon('precinct')}<span class="compact-filter-value" data-precinct-name>${area?.name ?? SELECT_LABEL}</span><span class="compact-filter-value precinct-short" data-precinct-short aria-hidden="true">${area ? compactPrecinctName(area, contract.precincts) : SELECT_LABEL}</span><span class="compact-filter-arrow" aria-hidden="true"></span></button>`,
      summary,
    );
    const clearSlot = /** @type {HTMLElement|null} */ (
      root.querySelector('[data-precinct-clear-slot]')
    );
    if (clearSlot)
      render(
        area
          ? html`<button class="precinct-clear" type="button" data-precinct-clear aria-label="Clear precinct selection" @click=${() => choose(null)}>Clear precinct selection</button>`
          : nothing,
        clearSlot,
      );
    root.closest('[data-compact-filters]')?.dispatchEvent(new Event('compact-filter-fit'));
    const warning =
      selection.status === 'invalid'
        ? 'Precinct not recognized. Showing ordinary browsing.'
        : storageWarning;
    render(html`${warning}`, notice);
    notice.hidden = warning === '';
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
  render(
    html`<div class="filter-select-control"><label class="filter-control-label" for="voting-precinct">${lookup ? 'Address or precinct' : 'Precinct'}</label><input class="filter-select" id="voting-precinct" data-ballot-search role="combobox" aria-autocomplete="list" aria-controls="ballot-options" aria-expanded="false" autocomplete="off" maxlength="300" @input=${edit} @keydown=${key} @compositionstart=${() => {
      composing = true;
      edit();
    }} @compositionend=${() => {
      composing = false;
      edit();
    }}><ul id="ballot-options" class="ballot-options" data-ballot-options role="listbox" aria-label="Matching addresses and precincts" hidden></ul></div>${lookup ? html`<p class="address-privacy">Typed text goes to King County GIS; selected address and coordinates go to county-maintained Esri services. Providers may retain requests. SEG remembers only your precinct.</p>` : nothing}`,
    fields,
  );
  submit.textContent = SELECT_LABEL;
  const heading = dialog.querySelector('h2');
  if (heading && lookup) heading.textContent = 'Select an address or precinct';
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    if (draft && !composing) choose(draft.code);
  });
  cancel.addEventListener('click', () => {
    discard();
    dialog.close();
    restoreFocus();
  });
  dialog.addEventListener('cancel', discard);
  viewport?.addEventListener('resize', fitViewport);
  viewport?.addEventListener('scroll', fitViewport);
  document.defaultView?.addEventListener('resize', fitViewport);
  dialog.addEventListener('scroll', fitOptions);
  dialog.addEventListener('keydown', (event) => {
    if (event.key !== 'Tab') return;
    const targets = /** @type {HTMLElement[]} */ ([
      ...dialog.querySelectorAll('a[href], input, button:not(:disabled)'),
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
    if (dialog.open) return;
    discard();
    restoreFocus();
  });
  root.removeAttribute('hidden');
  const initial = readPrecinctSelection(router.controlSearch(), contract);
  if (initial.status === 'absent')
    router.replaceControlSearch(
      withPrecinct(
        router.controlSearch(),
        resolvePrecinct(contract, loadPrecinct(contract.election_id)).code,
      ),
    );
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
