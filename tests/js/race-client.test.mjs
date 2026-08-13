// race-client.mjs is a race page's wiring (issue #136).
//
// `race-markup-parity.test.mjs` holds what it renders to what the server
// rendered, on real published pages. What is here is the behavior a fixture
// cannot show: what a selection does to the page, where the Sources link
// points, and what the reader is told when the link they followed cannot be
// used.

import assert from 'node:assert/strict';
import test from 'node:test';
import { installDom } from './support/dom.mjs';
import { assertModuleGuard } from './support/module-guards.mjs';

const RACE_URL = 'https://seattleelections.guide/e/wa-2026-primary/races/mayor/';

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

/** @param {any} [personalization] */
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
    race: {
      race_id: 'mayor',
      race_label: 'Seattle Mayor',
      race_path: '/e/wa-2026-primary/races/mayor/',
      audited_accessible_summary: 'The audited summary, verbatim.',
      candidates: [
        {
          candidate_id: 'ada',
          label: 'Ada Lovelace',
          endorsers: [
            {
              code: 'strn',
              name: 'The Stranger',
              category: 'press',
              category_label: 'Press',
              state: 'endorsement',
              panel_role: 'consensus',
              detail_label: null,
              evidence_url: 'https://example.test/stranger',
            },
          ],
          // A certified result (docs/RESULTS.md, Rendering § The endorsements
          // dialog; #287): selection-independent, so it is unaffected by
          // whichever candidate a lens currently recommends. Ada's own
          // outcome advanced; Blaise's did not — deliberately the opposite of
          // the audited tie, so a test that narrows the selection to Blaise
          // alone (making Blaise the *scored* leader) can prove the headline
          // chip follows the *certified* outcome, not the current selection.
          result: { percentage_label: '54.2%', advanced: true, chip_label: 'Advances' },
        },
        {
          candidate_id: 'blaise',
          label: 'Blaise Pascal',
          endorsers: [
            {
              code: 'mlkl',
              name: 'MLK Labor',
              category: 'press',
              category_label: 'Press',
              state: 'endorsement',
              panel_role: 'consensus',
              detail_label: null,
              evidence_url: 'https://example.test/mlk',
            },
          ],
          result: { percentage_label: '45.8%', advanced: false, chip_label: null },
        },
      ],
    },
    personalization,
  });
}

// The audited baseline the regions are taken over from, as race.html.j2
// renders it, reduced to the elements the wiring addresses.
const MARKUP = `
  <div class="lens-banner" data-lens-banner>
    <span data-lens-banner-status role="status" aria-live="polite">Counting all 2 sources.</span>
    <a data-sources-link href="/e/wa-2026-primary/sources/">Edit sources</a>
  </div>
  <p class="lens-notice" data-lens-notice hidden role="status" aria-live="polite"></p>
  <main data-publication-race-id="mayor">
    <div class="race-headline" role="group">
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
      <div class="race-headline-foot" data-lens-foot></div>
      <p id="race-consensus-summary" class="visually-hidden"
        data-race-detail-summary>The audited summary, verbatim.</p>
    </div>
    <div class="race-detail-outcomes">
      <div class="race-detail-candidates" data-race-candidates>
        <section class="race-detail-candidate" data-race-detail-candidate-id="ada"></section>
        <section class="race-detail-candidate" data-race-detail-candidate-id="blaise"></section>
      </div>
    </div>
  </main>`;

const document = installDom(RACE_URL);
const { wireRacePage } = await import(
  '../../src/election_guide/rendering/templates/race-client.mjs'
);

/**
 * @param {string} [fragment]
 * @param {any} [pagePayload]
 */
function build(fragment = '', pagePayload = payload()) {
  document.documentElement.innerHTML = `<head></head><body>${MARKUP}</body>`;
  // One window serves every test here (lit-html binds its document once per
  // process), and the root's class list outlives an innerHTML replacement — so
  // a page that a previous test personalized would start personalized.
  document.documentElement.className = '';
  window.location.hash = fragment;
  wireRacePage(pagePayload);
  return document;
}

/** A same-version selection fragment naming exactly `codes`. */
const lensFragment = (/** @type {readonly string[]} */ codes) =>
  `#lens=2&mode=s&panel=panel-v1&ph=${'a'.repeat(12)}&data=v1&scoring=equal-weight` +
  `&sel=${codes.join('')}`;

/** @param {string} fragment */
function goTo(fragment) {
  window.location.hash = fragment;
  window.dispatchEvent(new Event('hashchange'));
}

test('the audited default leaves every region as the server rendered it', () => {
  build();

  assert.equal(document.documentElement.classList.contains('lens-personalized'), false);
  assert.equal(
    document.querySelector('[data-lens-result] h3').textContent,
    'Ada Lovelace / Blaise Pascal',
  );
  assert.equal(
    document.querySelectorAll('[data-race-candidates] [data-race-detail-source-code]').length,
    0,
    'the audited render should not have rebuilt the server-rendered sections',
  );
  assert.equal(
    document.querySelector('[data-lens-banner-status]').textContent,
    'Counting all 2 sources.',
  );
});

test('a narrowed selection rescores the race and says what it is counting', () => {
  build(lensFragment(['mlkl']));

  assert.equal(document.documentElement.classList.contains('lens-personalized'), true);
  assert.equal(document.querySelector('[data-lens-result] h3').textContent, 'Blaise Pascal');
  // The headline states no count: this candidate's endorsing sources are the
  // rows listed directly below it, so a caption naming how many there are would
  // restate the list. The strip is what says what is being counted.
  assert.equal(document.querySelector('[data-lens-context] .support-line'), null);
  assert.equal(
    document.querySelector('[data-lens-banner-status]').textContent,
    'Counting 1 of 2 sources.',
  );
  // The leader the selection produced is first, whatever the audited order was
  // (#141 item 1: the sections follow the result on screen).
  assert.deepEqual(
    [...document.querySelectorAll('[data-race-detail-candidate-id]')].map(
      (section) => section.dataset.raceDetailCandidateId,
    ),
    ['blaise', 'ada'],
  );
});

// The certified vote-share row and heading chip (docs/RESULTS.md, Rendering §
// The race-detail page; #287) are selection-independent, so a personalized
// re-render has to reproduce them exactly as `race-detail.mjs`'s own coverage
// proves in isolation — this is the end-to-end wiring through `wireRacePage`,
// including the payload's snake_case-to-camelCase reshape and the headline
// chip lookup that has to follow whichever candidate a lens currently scores
// as the sole leader, not always the one the certified result favors.
test('a selection can headline the candidate whose own certified result did not advance', () => {
  build(lensFragment(['mlkl']));

  // Blaise is the *scored* leader under this selection (proven above), but
  // Blaise's own certified result never advanced — the headline carries no
  // chip at all, exactly as the audited render would for this candidate.
  assert.equal(
    document.querySelector('[data-lens-result] h3').textContent,
    'Blaise Pascal',
    'no chip text appended for a non-advancing headline candidate',
  );
  assert.equal(document.querySelector('[data-lens-result] .race-detail-result-chip'), null);

  // Every section still carries its own fixed vote-share row and chip,
  // unaffected by which sources are selected: Ada's own certified 54.2%
  // "Advances" outcome renders in her own section regardless of her not
  // being scored the leader here.
  const adaSection = document.querySelector('[data-race-detail-candidate-id="ada"]');
  const adaChip = adaSection.querySelector('.race-detail-result-chip');
  assert.ok(adaChip, "a candidate's own result renders regardless of the active selection");
  assert.equal(adaChip.textContent, 'Advances');
  assert.equal(adaSection.querySelector('.race-detail-result-share').textContent, '54.2%');

  const blaiseSection = document.querySelector('[data-race-detail-candidate-id="blaise"]');
  assert.equal(blaiseSection.querySelector('.race-detail-result-chip'), null);
  assert.equal(
    blaiseSection.querySelector('.race-detail-candidate-result').getAttribute('class'),
    'race-detail-candidate-result race-detail-candidate-result-trailing',
  );

  // Clearing the lens restores the audited tie headline, still with no chip
  // (a tie names two candidates, so no single candidate's own result could
  // attach to it even though Ada's own result did advance).
  goTo(lensFragment(['strn', 'mlkl']));
  assert.equal(
    document.querySelector('[data-lens-result] h3').textContent,
    'Ada Lovelace / Blaise Pascal',
  );
  assert.equal(document.querySelector('[data-lens-result] .race-detail-result-chip'), null);
});

// I56: an unselected source stays visible as evidence, marked as not counted,
// and no quantity appears with two values.
test('an unselected source stays in place, marked as not counted', () => {
  build(lensFragment(['mlkl']));

  const dropped = document.querySelector('[data-race-detail-source-code="strn"]');
  assert.ok(dropped, 'the deselected source must still be listed as evidence');
  assert.equal(dropped.classList.contains('race-detail-source-row-not-counted'), true);
  assert.equal(dropped.querySelector('.race-detail-source-not-counted').textContent, 'Not counted');

  const counted = document.querySelector('[data-race-detail-source-code="mlkl"]');
  assert.equal(counted.classList.contains('race-detail-source-row-not-counted'), false);
  assert.equal(counted.querySelector('.race-detail-source-not-counted'), null);
});

test('the visually-hidden summary is recomputed with the visible result', () => {
  build(lensFragment(['mlkl']));
  const summary = document.querySelector('[data-race-detail-summary]').textContent;

  assert.notEqual(summary, 'The audited summary, verbatim.');
  assert.match(summary, /^Blaise Pascal\./);
  assert.match(summary, /100%/);
});

test('clearing the lens restores the audited values and the published summary', () => {
  build(lensFragment(['mlkl']));
  goTo(lensFragment(['strn', 'mlkl']));

  assert.equal(document.documentElement.classList.contains('lens-personalized'), false);
  assert.equal(
    document.querySelector('[data-lens-result] h3').textContent,
    'Ada Lovelace / Blaise Pascal',
  );
  assert.equal(
    document.querySelector('[data-race-detail-summary]').textContent,
    'The audited summary, verbatim.',
  );
  assert.equal(document.querySelector('[data-race-detail-source-code="strn"]').className, '');
});

// G24–G27: "differs" means the leading choice itself changed, and the tint is
// never the only carrier.
test('a selection that changes the leader discloses the full panel, in words', () => {
  build(lensFragment(['mlkl']));
  const bar = document.querySelector('[data-lens-foot] .lens-comparison');

  assert.ok(bar, 'a divergent race should render the All-sources reference bar');
  assert.match(bar.textContent, /^All sources: /);
  assert.match(
    bar.getAttribute('aria-label'),
    /All sources (differ from|agree with) your selection/,
  );
});

// Issue 142, from the other end: the reader's selection has to survive a trip
// to the sources editor and back to this race.
test('the Sources link carries the live selection and this race as the way back', () => {
  build(lensFragment(['mlkl']));
  const href = document.querySelector('[data-sources-link]').getAttribute('href');

  assert.ok(href.startsWith('/e/wa-2026-primary/sources/#'), href);
  assert.match(href, /sel=mlkl/);
  assert.match(href, /race=race-mayor/);
});

test('the audited default carries only the race back, with no lens to write', () => {
  build();
  assert.equal(
    document.querySelector('[data-sources-link]').getAttribute('href'),
    '/e/wa-2026-primary/sources/#race-mayor',
  );
});

// docs/FRONTEND.md § State and URLs: a decode failure produces a
// reader-visible notice *and* a cleaned address bar. Neither half alone.
test('a link this build cannot read is reported and cleaned away', () => {
  build('#lens=2&mode=s&panel=panel-v1&ph=aaaaaaaaaaaa&data=v1&scoring=equal-weight&sel=zzzz');
  const notice = document.querySelector('[data-lens-notice]');

  assert.equal(notice.hidden, false);
  assert.match(notice.textContent, /could not be read/);
  assert.equal(window.location.hash, '');
  assert.equal(
    document.querySelector('[data-lens-result] h3').textContent,
    'Ada Lovelace / Blaise Pascal',
    'an unreadable link resolves to the audited consensus',
  );
});

test('an ordinary in-page anchor raises no notice at all', () => {
  build('#race-detail');
  assert.equal(document.querySelector('[data-lens-notice]').hidden, true);
});

test('a page whose release policy disables the lens renders nothing extra', () => {
  build(lensFragment(['mlkl']), payload(null));

  assert.equal(document.documentElement.classList.contains('lens-personalized'), false);
  assert.equal(
    document.querySelector('[data-lens-result] h3').textContent,
    'Ada Lovelace / Blaise Pascal',
  );
});

test('the module keeps client state out of storage', () => {
  assertModuleGuard('race-client.mjs');
});
