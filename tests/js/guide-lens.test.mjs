// guide-lens.mjs is the guide's personalized rendering, moved out of
// guide.html.j2's module script by issue #239. It is still imperative DOM
// writing — the lit-html conversion is issue #248 — so these tests pin the
// behavior the move had to preserve, in a lightweight DOM
// (docs/FRONTEND.md § Testing).

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

function lensMarkup() {
  return `
    <div data-lens-banner hidden><span data-lens-banner-status></span></div>
    <article id="race-mayor" data-publication-race-id="mayor">
      <h3 data-lens-recommendation></h3>
      <div data-lens-share><strong data-lens-share-text></strong></div>
      <p data-lens-no-majority hidden></p>
      <p data-lens-support></p>
      <p data-lens-support-compact></p>
      <div data-lens-insufficient hidden></div>
      <p data-lens-comparison hidden></p>
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

test('the audited default reveals the banner and renders no personalized values', async () => {
  const { document, lens } = await build();
  lens.render(['strn', 'mlkl']);

  assert.equal(document.querySelector('[data-lens-banner]').hidden, false);
  assert.equal(
    document.querySelector('[data-lens-banner-status]').textContent,
    'Counting all 2 sources.',
  );
  assert.equal(document.documentElement.classList.contains('lens-personalized'), false);
  assert.equal(document.querySelector('[data-lens-recommendation]').textContent, '');
});

test('a narrowed selection renders the personalized result and counts', async () => {
  const { document, lens } = await build();
  lens.render(['strn']);

  assert.equal(document.documentElement.classList.contains('lens-personalized'), true);
  assert.equal(
    document.querySelector('[data-lens-banner-status]').textContent,
    'Counting 1 of 2 sources.',
  );
  assert.equal(document.querySelector('[data-lens-recommendation]').textContent, 'Ada Lovelace');
  assert.equal(document.querySelector('[data-lens-share-text]').textContent, '100%');
  assert.equal(
    document.querySelector('[data-lens-support]').textContent,
    'Based on 1 of 1 selected sources',
  );
});

test('the meter carries the fill, the tone, and the spoken label together', async () => {
  const { document, lens } = await build();
  lens.render(['strn']);
  const meter = document.querySelector('[data-lens-share]');

  assert.equal(meter.style.getPropertyValue('--meter-fill'), '100%');
  assert.equal(meter.classList.contains('meter-no-majority'), false);
  assert.match(meter.getAttribute('aria-label'), /Consensus among explicitly endorsing sources/);
});

// G24–G27: "differs" means the leading choice itself changed, and the tint is
// never the only carrier.
test('a race whose leader changed discloses the full-panel reference, in words', async () => {
  const { document, lens } = await build();
  lens.render(['mlkl']);
  const bar = document.querySelector('[data-lens-comparison]');

  assert.equal(bar.hidden, false);
  assert.match(bar.textContent, /^All sources: /);
  assert.match(
    bar.getAttribute('aria-label'),
    /All sources (differ from|agree with) your selection/,
  );
  // The dialog carries the same reference line (I56).
  assert.equal(document.querySelector('[data-lens-detail-audited]').hidden, false);
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
test('reselecting every source restores the audited order and summary', async () => {
  const { document, lens } = await build();
  lens.render(['mlkl']);
  assert.notEqual(
    document.querySelector('[data-race-detail-summary]').textContent,
    'The audited summary, verbatim.',
  );

  lens.render(['strn', 'mlkl']);
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

test('the module keeps client state out of storage', () => {
  assertModuleGuard('guide-lens.mjs');
});
