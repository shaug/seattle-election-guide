// guide-lens.mjs is the guide's personalized rendering. Since issue #248 the
// race card's three regions are lit-html templates over view-model state and
// only the race-detail dialog is still patched by hand, so these tests read the
// rendered markup rather than the twin elements that used to hold it, in a
// lightweight DOM (docs/FRONTEND.md § Testing).
//
// The banner is not here: it is page chrome, and `guide-client.test.mjs` covers
// the region that owns it.

import assert from 'node:assert/strict';
import test from 'node:test';
import { installDom } from './support/dom.mjs';
import { assertModuleGuard } from './support/module-guards.mjs';

const GUIDE_URL = 'https://seattleelections.guide/e/wa-2026-primary/';

/**
 * Two sources, one race, two candidates. `strn` endorses Ada, `mlkl` endorses
 * Blaise, so deselecting either one changes the leader — the divergence the
 * reference bar exists to report.
 */
function personalizationContract() {
  return {
    panel_id: 'panel-v1',
    panel_hash: 'a'.repeat(64),
    panel_version: 1,
    retired_codes: [],
    // The scoring shape the audited engine publishes, reduced to what one race
    // exercises. `minimum_explicit_sources: 1` keeps a single-source lens out of
    // the Insufficient grade, which is the state under test here.
    scoring: {
      allocation: 'exact_equal_split',
      configuration_id: 'equal-weight',
      grades: [
        { grade: 'A', minimum_explicit_sources: null, minimum_share: '3/4' },
        { grade: 'D', minimum_explicit_sources: null, minimum_share: '0' },
      ],
      insufficient_precedes_ordinary_grade: true,
      minimum_explicit_sources: 1,
      missing_coverage_enters_denominator: false,
      no_endorsement_enters_denominator: false,
      tie_precedes_grade: true,
    },
    policy: { maximum_url_characters: 4096, enabled: true },
    categories: [
      {
        id: 'press',
        code: 'Gprs',
        label: 'Press',
        selectable: true,
        panel_role: 'tallying',
        member_source_codes: ['strn', 'mlkl'],
      },
    ],
    sources: [
      {
        id: 'stranger',
        code: 'strn',
        selectable: true,
        panel_role: 'consensus',
        reporting_category_id: 'press',
        selection_category_ids: ['press'],
        overlap_group_ids: [],
      },
      {
        id: 'mlk',
        code: 'mlkl',
        selectable: true,
        panel_role: 'consensus',
        reporting_category_id: 'press',
        selection_category_ids: ['press'],
        overlap_group_ids: [],
      },
    ],
    races: [
      {
        race_id: 'mayor',
        candidate_order: ['ada', 'blaise'],
        eligible_source_codes: ['strn', 'mlkl'],
        cells: [
          { source_code: 'strn', state: 'endorsement', allocation: { ada: '1' } },
          { source_code: 'mlkl', state: 'endorsement', allocation: { blaise: '1' } },
        ],
      },
    ],
  };
}

function payload(personalization = personalizationContract()) {
  const contract = personalization ?? personalizationContract();
  return /** @type {any} */ ({
    schema_version: '1.0',
    data_version: 'v1',
    panel_id: contract.panel_id,
    panel_hash: contract.panel_hash,
    policy: { maximum_url_characters: 4096 },
    scoring: contract.scoring,
    categories: contract.categories,
    sources: contract.sources,
    sources_page_path: '/e/wa-2026-primary/sources/',
    filter_scopes: [{ value: 'all', label: 'All Seattle ballot races' }],
    races: [
      {
        race_id: 'mayor',
        race_label: 'Seattle Mayor',
        candidates: [
          { candidate_id: 'ada', label: 'Ada Lovelace' },
          { candidate_id: 'blaise', label: 'Blaise Pascal' },
        ],
        audited_accessible_summary: 'The audited summary, verbatim.',
      },
    ],
    personalization,
  });
}

// The audited baseline the card regions are taken over from, as guide.html.j2
// renders it: one element per value, holding the audited result.
function lensMarkup() {
  return `
    <article id="race-mayor" data-publication-race-id="mayor">
      <div class="screen-race-result" data-lens-result>
        <h3 data-display-role="recommendation">Ada Lovelace / Blaise Pascal</h3>
        <div class="screen-meter meter-no-majority" style="--meter-fill: 50%" role="img"
          data-display-role="share"
          aria-label="No majority. Consensus among explicitly endorsing sources: 50%">
          <strong>50%</strong>
        </div>
      </div>
      <div class="screen-race-context" data-lens-context>
        <p class="no-majority-pill">No majority</p>
        <p class="support-line support-full" data-display-role="support">Based on 2 endorsing sources</p>
        <p class="support-line support-compact" data-display-role="support">2 sources</p>
      </div>
      <div class="race-card-foot" data-lens-foot></div>
      <dialog data-race-detail-dialog>
        <p data-race-detail-summary>The audited summary, verbatim.</p>
        <div class="race-detail-outcomes">
          <section data-race-detail-candidate-id="ada">
            <p data-race-detail-lens-kicker hidden></p>
            <span data-race-detail-lens-count></span>
            <div data-race-detail-lens-meter hidden>
              <strong data-race-detail-lens-meter-text></strong>
            </div>
            <li data-endorsed-candidate-id="ada" data-race-detail-source-code="strn">
              <span data-race-detail-not-counted hidden></span>
            </li>
          </section>
          <section data-race-detail-candidate-id="blaise">
            <p data-race-detail-lens-kicker hidden></p>
            <span data-race-detail-lens-count></span>
            <div data-race-detail-lens-meter hidden>
              <strong data-race-detail-lens-meter-text></strong>
            </div>
            <li data-endorsed-candidate-id="blaise" data-race-detail-source-code="mlkl">
              <span data-race-detail-not-counted hidden></span>
            </li>
          </section>
          <p data-lens-detail-audited hidden></p>
        </div>
      </dialog>
    </article>`;
}

/** @param {any} [pagePayload] */
async function build(pagePayload = payload()) {
  const document = installDom(GUIDE_URL);
  document.body.innerHTML = lensMarkup();
  const { createGuideLens } = await import(
    '../../src/election_guide/rendering/templates/guide-lens.mjs'
  );
  return { document, lens: createGuideLens(pagePayload) };
}

test('a page with the lens disabled has no renderer at all', async () => {
  const { lens } = await build(payload(null));
  assert.equal(lens, null);
});

// The takeover idiom (docs/FRONTEND.md § Rendering): a region whose content is
// a projection of state is left exactly as the server rendered it until the
// state stops being the audited default.
test('the audited default leaves every card region as the server rendered it', async () => {
  const { document, lens } = await build();
  const before = document.querySelector('[data-lens-result] h3');
  lens.render(['strn', 'mlkl']);

  assert.equal(document.documentElement.classList.contains('lens-personalized'), false);
  assert.ok(
    document.querySelector('[data-lens-result] h3') === before,
    'the client rebuilt a card region at the audited default',
  );
  assert.equal(before.textContent, 'Ada Lovelace / Blaise Pascal');
});

test('a narrowed selection renders the personalized result and counts', async () => {
  const { document, lens } = await build();
  lens.render(['strn']);

  assert.equal(document.documentElement.classList.contains('lens-personalized'), true);
  assert.equal(document.querySelector('[data-lens-result] h3').textContent, 'Ada Lovelace');
  assert.equal(
    document.querySelector('[data-lens-result] .screen-meter strong').textContent,
    '100%',
  );
  assert.equal(
    document.querySelector('[data-lens-context] .support-full').textContent,
    'Based on 1 of 1 selected sources',
  );
  assert.equal(
    document.querySelector('[data-lens-context] .support-compact').textContent,
    '1 of 1 selected',
  );
  assert.equal(document.querySelector('[data-lens-context] .no-majority-pill').hidden, true);
});

test('the meter carries the fill, the tone, and the spoken label together', async () => {
  const { document, lens } = await build();
  lens.render(['strn']);
  const meter = document.querySelector('[data-lens-result] .screen-meter');

  assert.equal(meter.getAttribute('style'), '--meter-fill: 100%');
  assert.equal(meter.classList.contains('meter-no-majority'), false);
  assert.match(meter.getAttribute('aria-label'), /Consensus among explicitly endorsing sources/);
});

// G24–G27: "differs" means the leading choice itself changed, and the tint is
// never the only carrier.
test('a race whose leader changed discloses the full-panel reference, in words', async () => {
  const { document, lens } = await build();
  lens.render(['mlkl']);
  const bar = document.querySelector('[data-lens-foot] .lens-comparison');

  assert.ok(bar, 'a divergent race should render the All-sources reference bar');
  assert.match(bar.textContent, /^All sources: /);
  assert.equal(bar.getAttribute('role'), 'group');
  assert.match(
    bar.getAttribute('aria-label'),
    /All sources (differ from|agree with) your selection/,
  );
  // The dialog carries the same reference line (I56).
  assert.equal(document.querySelector('[data-lens-detail-audited]').hidden, false);
});

// The bar is divergence-only, so an unchanged race renders no element at all
// rather than an empty one waiting to be filled in.
test('a selection that changes nothing renders no reference bar', async () => {
  const { document, lens } = await build();
  lens.render(['mlkl']);
  assert.ok(document.querySelector('[data-lens-foot] .lens-comparison'));

  lens.render(['strn', 'mlkl']);
  assert.equal(document.querySelector('[data-lens-foot] .lens-comparison'), null);
});

// I56: no quantity may appear with two values, and an unselected source stays
// in place as evidence rather than being removed.
test('an unselected source stays visible, marked as not counted', async () => {
  const { document, lens } = await build();
  lens.render(['strn']);
  const dropped = document.querySelector('[data-race-detail-source-code="mlkl"]');

  assert.equal(dropped.classList.contains('race-detail-source-row-not-counted'), true);
  assert.equal(dropped.querySelector('[data-race-detail-not-counted]').hidden, false);
  assert.equal(dropped.querySelector('[data-race-detail-not-counted]').textContent, 'Not counted');

  const kept = document.querySelector('[data-race-detail-source-code="strn"]');
  assert.equal(kept.classList.contains('race-detail-source-row-not-counted'), false);
  assert.equal(kept.querySelector('[data-race-detail-not-counted]').hidden, true);
});

// Ticket #141 item 1: the dialog's candidate order follows the displayed result.
test('the leading candidate is moved to the front of the dialog', async () => {
  const { document, lens } = await build();
  lens.render(['mlkl']);
  const order = [
    ...document.querySelectorAll('.race-detail-outcomes > [data-race-detail-candidate-id]'),
  ].map((section) => section.dataset.raceDetailCandidateId);
  assert.deepEqual(order, ['blaise', 'ada']);
});

// The restore this ticket had to keep: nothing runs the renderer once the lens
// stops applying, so clearing it must put the audited order and summary back.
test('reselecting every source restores the audited order, values, and summary', async () => {
  const { document, lens } = await build();
  lens.render(['mlkl']);
  assert.notEqual(
    document.querySelector('[data-race-detail-summary]').textContent,
    'The audited summary, verbatim.',
  );
  assert.equal(document.querySelector('[data-lens-result] h3').textContent, 'Blaise Pascal');

  lens.render(['strn', 'mlkl']);
  // The audited restore is a render of the audited view model, not a copy of
  // the server's markup put back (docs/FRONTEND.md § Rendering).
  assert.equal(
    document.querySelector('[data-lens-result] h3').textContent,
    'Ada Lovelace / Blaise Pascal',
  );
  assert.equal(document.querySelector('[data-lens-context] .no-majority-pill').hidden, false);
  assert.equal(
    document.querySelector('[data-lens-context] .support-full').textContent,
    'Based on 2 endorsing sources',
  );
  const order = [
    ...document.querySelectorAll('.race-detail-outcomes > [data-race-detail-candidate-id]'),
  ].map((section) => section.dataset.raceDetailCandidateId);
  assert.deepEqual(order, ['ada', 'blaise']);
  assert.equal(
    document.querySelector('[data-race-detail-summary]').textContent,
    'The audited summary, verbatim.',
  );
});

// Ticket #141 item 5: the visually-hidden summary must not disagree with the
// visible numbers while a lens is active.
test('the accessible summary is recomputed with the visible result', async () => {
  const { document, lens } = await build();
  lens.render(['strn']);
  const summary = document.querySelector('[data-race-detail-summary]').textContent;
  assert.match(summary, /^Ada Lovelace\./);
  assert.match(summary, /100%/);
});

test('the audited candidate order and labels come from the payload', async () => {
  // A payload whose audited order is the reverse of the rendered markup proves
  // the restore reads the contract, not the DOM it was handed.
  const reversed = payload();
  reversed.races[0].candidates = [
    { candidate_id: 'blaise', label: 'Blaise Pascal' },
    { candidate_id: 'ada', label: 'Ada Lovelace' },
  ];
  const { document, lens } = await build(reversed);
  lens.render(['strn', 'mlkl']);
  const order = [
    ...document.querySelectorAll('.race-detail-outcomes > [data-race-detail-candidate-id]'),
  ].map((section) => section.dataset.raceDetailCandidateId);
  assert.deepEqual(order, ['blaise', 'ada']);
});

// The Insufficient branch of the card foot, which nothing else reaches: no
// race on the published ballot carries that grade, so the markup-parity fixture
// cannot exercise it either. Both wordings are mirrors of the audited renderer
// — the audited one of guide.html.j2's literal, the personalized one of the
// sentence the retired lens-only twin used to carry — so they are asserted here
// rather than left to a whole-document search that the inlined bundle would
// satisfy on its own (docs/FRONTEND.md § Cross-language mirrors).
test('an insufficient race states the shortage, in the wording that applies', async () => {
  // Three endorsing sources required, so both the one-source lens and the
  // two-source audited baseline fall short. Both sources back Ada here: a tie
  // outranks Insufficient in the grade order, and a tied audited baseline would
  // never reach the audited wording.
  const strict = payload();
  strict.personalization.scoring.minimum_explicit_sources = 3;
  strict.personalization.races[0].cells[1].allocation = { ada: '1' };
  const { document, lens } = await build(strict);
  const note = () => document.querySelector('[data-lens-foot] .insufficient-note');

  lens.render(['strn']);
  assert.equal(
    note().textContent,
    'Too few endorsements to measure agreement among your selected sources.',
  );
  assert.equal(note().getAttribute('role'), 'note');

  // The audited restore is a render, so it must put the server's own wording
  // back rather than leaving the personalized sentence behind.
  lens.render(['strn', 'mlkl']);
  assert.equal(note().textContent, 'Too few endorsements to measure agreement.');
});

// I41's threshold is a Python/JavaScript mirror — guide.html.j2 writes
// `race.percentage_whole < 30`, meterView writes `fillPercent < 30` — and the
// markup-parity fixture cannot reach it, because no race on the published
// ballot has a sub-30% leader (docs/FRONTEND.md § Cross-language mirrors: the
// diff "cannot reach a value the audited page does not render"). So the
// decision is exercised here, through meterView, rather than restated in a
// fixture that would agree with whatever production chose.
test('a share below the I41 threshold carries the low-fill guard', async () => {
  // Five sources, four candidates. The audited baseline gives Ada two of five
  // (40%, above the threshold); dropping her second endorser leaves a four-way
  // tie at 25%, below it.
  const spread = payload();
  const codes = ['strn', 'mlkl', 'urbn', 'kcdm', 'sicl'];
  spread.personalization.sources = codes.map((code) => ({
    id: code,
    code,
    selectable: true,
    panel_role: 'consensus',
    reporting_category_id: 'press',
    selection_category_ids: ['press'],
    overlap_group_ids: [],
  }));
  spread.personalization.categories[0].member_source_codes = codes;
  spread.personalization.races[0].candidate_order = ['ada', 'blaise', 'carol', 'dave'];
  spread.personalization.races[0].eligible_source_codes = codes;
  spread.personalization.races[0].cells = [
    { source_code: 'strn', state: 'endorsement', allocation: { ada: '1' } },
    { source_code: 'mlkl', state: 'endorsement', allocation: { blaise: '1' } },
    { source_code: 'urbn', state: 'endorsement', allocation: { carol: '1' } },
    { source_code: 'kcdm', state: 'endorsement', allocation: { dave: '1' } },
    { source_code: 'sicl', state: 'endorsement', allocation: { ada: '1' } },
  ];
  spread.sources = spread.personalization.sources;
  spread.categories = spread.personalization.categories;
  spread.races[0].candidates = ['ada', 'blaise', 'carol', 'dave'].map((candidate_id) => ({
    candidate_id,
    label: candidate_id,
  }));

  const { document, lens } = await build(spread);
  const meter = () => document.querySelector('[data-lens-result] .screen-meter');

  lens.render(['strn', 'mlkl', 'urbn', 'kcdm']);
  assert.equal(meter().querySelector('strong').textContent, '25%');
  assert.ok(
    meter().classList.contains('meter-low-fill'),
    'a 25% share is below the I41 threshold and must carry the low-fill guard',
  );

  // The audited restore renders 40%, which is above it.
  lens.render(codes);
  assert.equal(meter().querySelector('strong').textContent, '40%');
  assert.equal(meter().classList.contains('meter-low-fill'), false);
});

test('the module keeps client state out of storage', () => {
  assertModuleGuard('guide-lens.mjs');
});
