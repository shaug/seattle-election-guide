import { html, nothing, render } from 'lit-html';
import { live } from 'lit-html/directives/live.js';
import { repeat } from 'lit-html/directives/repeat.js';
import { admitProfile, resolveBallot } from './ballot-membership.mjs';
import { readBallotProfile, writeBallotProfile } from './ballot-profile-store.mjs';

/** @typedef {import('./ballot-profile-store.mjs').SavedBallot} SavedBallot */
/** @typedef {{active:boolean, membership:Record<string,import('./ballot-membership.mjs').Membership>, complete:boolean, resetRestrictions?:boolean}} BallotState */
/** @param {BallotMembershipContract|null|undefined} contract
 * @param {(state:BallotState)=>void} onChange
 * @param {{read?:typeof readBallotProfile, write?:typeof writeBallotProfile}} [store] */
export function wireBallotSetup(contract, onChange, store = {}) {
  const root = document.querySelector(/** @type {'div'} */ ('[data-ballot-setup]'));
  const status = document.querySelector(/** @type {'p'} */ ('[data-ballot-status]'));
  if (!root || !status || !contract) return;
  root.replaceChildren();
  status.replaceChildren();
  /** @type {Record<string,string>} */
  let choices = {};
  let active = false;
  let edited = false;
  let saveNotice = '';
  let writes = Promise.resolve();
  /** @param {boolean} [resetRestrictions] */
  const update = (resetRestrictions = false) => {
    const result = resolveBallot(contract, choices);
    onChange({ active, ...result, resetRestrictions });
    render(
      html`${
        !active
          ? 'Browsing all Seattle contests.'
          : result.complete
            ? 'District setup complete. Showing matching contests in SEG’s Seattle inventory.'
            : 'District setup incomplete. Contests needing confirmation remain visible.'
      } ${saveNotice}`,
      status,
    );
    render(
      html`<details><summary>Set up your ballot</summary>
      <p>For voters registered in Seattle. Select each district independently.</p>
      <p><a href="https://kingcounty.gov/en/dept/elections/maps/find-my-district" target="_blank" rel="noopener">Find your districts with King County Elections</a> · <a href="https://info.kingcounty.gov/kcelections/vote/myvoterinfo.aspx" target="_blank" rel="noopener">Official voter information</a></p>
      <p>SEG matches contests in its published inventory. Check your official ballot for the complete list.</p>
      ${contract.inventory_notice ? html`<p>${contract.inventory_notice}</p>` : nothing}
      ${repeat(
        contract.groups,
        (group) => group.id,
        (
          group,
        ) => html`<label class="ballot-district">${group.mode === 'membership' ? `Do you vote in ${group.label}?` : group.label}
        <select .value=${live(choices[group.id] ?? '')} @change=${(/** @type {Event} */ event) => {
          const value = /** @type {HTMLSelectElement} */ (event.target).value;
          choices = { ...choices, [group.id]: value };
          active = true;
          edited = true;
          update();
          save();
        }}><option value="">I don’t know yet</option>${
          group.mode === 'membership'
            ? html`<option value="yes">Yes</option><option value="no">No</option>`
            : html`${group.options.map((option) => html`<option value=${option.id}>${option.label}</option>`)}<option value="other">My district is not listed</option>`
        }</select></label>`,
      )}
      <button type="button" @click=${() => {
        active = true;
        edited = true;
        update();
        save();
      }}>Show your ballot</button>
      <button type="button" @click=${() => {
        active = false;
        edited = true;
        update(true);
        save();
      }}>Browse all Seattle contests</button>
      <button type="button" @click=${() => {
        choices = {};
        active = false;
        edited = true;
        update(true);
        save(true);
      }}>Clear saved districts</button>
    </details>${active && !result.complete ? html`<p>“${contract.confirmation_label}” marks contests that may be on your ballot.</p>` : nothing}`,
      root,
    );
  };
  /** @param {boolean} [clear] */
  const save = (clear = false) => {
    const value = clear
      ? null
      : {
          version: /** @type {const} */ (1),
          mode: /** @type {'ballot'|'all'} */ (active ? 'ballot' : 'all'),
          choices: admitProfile(contract, choices),
        };
    writes = writes
      .then(() => (store.write ?? writeBallotProfile)(contract.election_id, value))
      .then(
        () => {
          saveNotice = '';
          update();
        },
        () => {
          saveNotice =
            'Your districts could not be remembered on this device. Your current selection still applies.';
          update();
        },
      );
  };
  update();
  void (store.read ?? readBallotProfile)(contract.election_id).then(
    (value) => {
      if (edited || !value || typeof value !== 'object') return;
      const saved = /** @type {Partial<SavedBallot>} */ (value);
      if (saved.version !== 1 || (saved.mode !== 'ballot' && saved.mode !== 'all')) return;
      choices = admitProfile(contract, saved.choices);
      active = saved.mode === 'ballot';
      update();
    },
    () => {
      saveNotice =
        'Saved districts are unavailable. You can still set up your ballot for this visit.';
      update();
    },
  );
}
