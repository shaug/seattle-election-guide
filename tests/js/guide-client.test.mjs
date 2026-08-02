// guide-client.mjs is what used to be guide.html.j2's two inline `<script>`
// blocks (issue #239). It composes; the behavior is in the four modules it
// calls, each tested beside it. What is tested here is the composition itself —
// the incoming link's resolution, the notices it produces, and the Sources links
// it keeps pointed at the reader's selection.

import assert from 'node:assert/strict';
import test from 'node:test';
import { SELECTION_LINK_FAILURE_NOTICE } from '../../src/election_guide/rendering/templates/lens-selection.mjs';
import { installDom } from './support/dom.mjs';
import { assertModuleGuard } from './support/module-guards.mjs';

const GUIDE_URL = 'https://seattleelections.guide/e/wa-2026-primary/';
const SOURCES_PATH = '/e/wa-2026-primary/sources/';
const PANEL_ID = 'wa-2026-primary-default-sources-v4';
const PANEL_HASH = '6cd4acaa0c5e4ed0b5ddd0134d7de2af5a54c2085e7ad463f9b575b8e6dcb43f';
const DATA_VERSION = 'd119ee3107bb';
const SCORING_ID = 'wa-2026-primary-equal-weight';

/** A same-version lens fragment naming `codes`. */
const lensFragment = (/** @type {string[]} */ codes) =>
  `lens=2&mode=s&panel=${PANEL_ID}&ph=${PANEL_HASH.slice(0, 12)}&data=${DATA_VERSION}` +
  `&scoring=${SCORING_ID}&sel=${codes.join('')}`;

function personalizationContract() {
  return {
    panel_id: PANEL_ID,
    panel_hash: PANEL_HASH,
    panel_version: 1,
    retired_codes: [],
    scoring: {
      allocation: 'exact_equal_split',
      configuration_id: SCORING_ID,
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
        member_source_codes: ['strn', 'urbn'],
      },
      {
        id: 'labor',
        code: 'Glab',
        label: 'Labor',
        selectable: true,
        panel_role: 'tallying',
        member_source_codes: ['mlkl'],
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
        id: 'urbanist',
        code: 'urbn',
        selectable: true,
        panel_role: 'consensus',
        reporting_category_id: 'press',
        selection_category_ids: ['press'],
        overlap_group_ids: [],
      },
      // Outside the Press category, so selecting that category is a strict
      // subset of the panel rather than the audited default.
      {
        id: 'mlk-labor',
        code: 'mlkl',
        selectable: true,
        panel_role: 'consensus',
        reporting_category_id: 'labor',
        selection_category_ids: ['labor'],
        overlap_group_ids: [],
      },
    ],
    races: [
      {
        race_id: 'mayor',
        candidate_order: ['ada', 'blaise'],
        eligible_source_codes: ['strn', 'urbn', 'mlkl'],
        cells: [
          { source_code: 'strn', state: 'endorsement', allocation: { ada: '1' } },
          { source_code: 'urbn', state: 'endorsement', allocation: { blaise: '1' } },
          { source_code: 'mlkl', state: 'endorsement', allocation: { ada: '1' } },
        ],
      },
    ],
  };
}

/** @param {Record<string, unknown>} [overrides] */
function payload(overrides = {}) {
  const personalization = personalizationContract();
  return /** @type {any} */ ({
    schema_version: '1.0',
    data_version: DATA_VERSION,
    panel_id: PANEL_ID,
    panel_hash: PANEL_HASH,
    policy: { maximum_url_characters: 4096 },
    scoring: { configuration_id: SCORING_ID },
    categories: personalization.categories,
    sources: personalization.sources,
    sources_page_path: SOURCES_PATH,
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
    ...overrides,
  });
}

function guideMarkup() {
  return `
    <select id="race-filter"><option value="all">All Seattle ballot races</option></select>
    <input type="radio" name="ballot-view" value="full" checked>
    <input type="radio" name="ballot-view" value="compact">
    <input type="radio" name="race-set" value="complete" id="complete-filter" checked>
    <input type="radio" name="race-set" value="contested">
    <p id="filter-status"></p>
    <div data-lens-banner hidden><span data-lens-banner-status></span></div>
    <a data-sources-link href="${SOURCES_PATH}">Edit sources</a>
    <p class="lens-notice" data-lens-notice hidden></p>
    <section data-filter-section="local">
      <article id="race-mayor" data-publication-race-id="mayor" data-contested="true"
        data-filter-tokens='["city"]'>
        <a href="#race-mayor" data-race-detail-link>Mayor</a>
        <h3 data-lens-recommendation></h3>
        <div data-lens-share><strong data-lens-share-text></strong></div>
        <p data-lens-support></p>
        <p data-lens-support-compact></p>
        <p data-lens-comparison hidden></p>
        <dialog data-race-detail-dialog data-race-id="mayor">
          <p data-race-detail-summary>The audited summary, verbatim.</p>
          <div class="race-detail-outcomes">
            <section data-race-detail-candidate-id="ada"></section>
            <section data-race-detail-candidate-id="blaise"></section>
          </div>
          <button type="button" data-close-race-detail></button>
        </dialog>
      </article>
    </section>`;
}

/**
 * @param {string} url
 * @param {any} [pagePayload]
 */
async function wire(url, pagePayload = payload()) {
  const document = installDom(url);
  document.body.innerHTML = guideMarkup();
  for (const dialog of document.querySelectorAll('dialog')) {
    dialog.showModal = function showModal() {
      this.open = true;
    };
    dialog.close = function close() {
      this.open = false;
    };
  }
  const { wireGuide } = await import(
    '../../src/election_guide/rendering/templates/guide-client.mjs'
  );
  wireGuide(pagePayload);
  return document;
}

const notice = (/** @type {Document} */ document) => document.querySelector('[data-lens-notice]');
const sourcesHref = (/** @type {Document} */ document) =>
  document.querySelector('[data-sources-link]').getAttribute('href');

test('the audited default renders with no notice and a bare Sources link', async () => {
  const document = await wire(GUIDE_URL);
  assert.equal(notice(document).hidden, true);
  assert.equal(sourcesHref(document), SOURCES_PATH);
  assert.equal(document.documentElement.classList.contains('lens-personalized'), false);
});

test('a same-version link applies its selection and explains nothing', async () => {
  const document = await wire(`${GUIDE_URL}#${lensFragment(['strn'])}`);
  assert.equal(notice(document).hidden, true);
  assert.equal(document.documentElement.classList.contains('lens-personalized'), true);
  assert.equal(document.querySelector('[data-lens-recommendation]').textContent, 'Ada Lovelace');
});

test('the Sources link carries the reader’s live selection', async () => {
  const document = await wire(`${GUIDE_URL}#${lensFragment(['strn'])}`);
  const href = sourcesHref(document);
  assert.ok(href.startsWith(`${SOURCES_PATH}#`));
  assert.match(href, /sel=strn/);
});

test('the Sources link is root-relative, so it never leaves the current origin', async () => {
  const document = await wire(`${GUIDE_URL}#${lensFragment(['strn'])}`);
  assert.ok(sourcesHref(document).startsWith('/e/'));
});

// A plain in-page anchor decodes the same way an unreadable lens does, and must
// not manufacture a notice or lose its own fragment.
test('an ordinary in-page anchor is left alone', async () => {
  const document = await wire(`${GUIDE_URL}#guide-races`);
  assert.equal(notice(document).hidden, true);
  assert.equal(window.location.hash, '#guide-races');
});

test('an unreadable link falls back to audited, says so, and cleans the address', async () => {
  const document = await wire(`${GUIDE_URL}#lens=9&mode=s&sel=strn`);
  assert.equal(notice(document).hidden, false);
  assert.match(notice(document).textContent, /could not be read/);
  assert.equal(window.location.hash, '');
  assert.equal(document.documentElement.classList.contains('lens-personalized'), false);
});

// The rule requires a notice *and* a cleaned address bar. With the lens
// disabled the old code did only the second half, in silence.
test('an unreadable link is reported even while personalization is disabled', async () => {
  const disabled = payload({ personalization: null });
  const document = await wire(`${GUIDE_URL}#lens=9&mode=s&sel=strn`, disabled);
  assert.equal(notice(document).hidden, false);
  assert.match(notice(document).textContent, /could not be read/);
  assert.equal(window.location.hash, '');
});

test('a stale-version link is migrated behind a persistent explanation', async () => {
  const stale = `lens=2&mode=s&panel=old-panel&ph=000000000000&data=old&scoring=${SCORING_ID}&sel=strn`;
  const document = await wire(`${GUIDE_URL}#${stale}`);
  assert.equal(notice(document).hidden, false);
  assert.match(notice(document).textContent, /earlier published data version/);
  assert.equal(document.documentElement.classList.contains('lens-personalized'), true);
});

// The silent loss this ticket fixes: a rejected encode used to leave the
// Sources link pointing at the bare guide with no indication the selection had
// been dropped.
//
// The reachable case, and the reason it is reachable: a category token is four
// characters and expands to every member source code, so re-encoding a link
// that arrived within the published limit can exceed it. The limit here is the
// incoming link's own length, so the arrival decodes and only the rewrite is
// refused.
test('a selection too large to encode says so instead of vanishing', async () => {
  const incoming = lensFragment(['Gprs']);
  const cramped = payload();
  cramped.policy = { maximum_url_characters: incoming.length };
  cramped.personalization.policy = {
    maximum_url_characters: incoming.length,
    enabled: true,
  };
  const document = await wire(`${GUIDE_URL}#${incoming}`, cramped);

  assert.equal(notice(document).hidden, false);
  assert.equal(notice(document).textContent, SELECTION_LINK_FAILURE_NOTICE);
  // The page still shows the selection the link asked for; only the link out
  // could not carry it.
  assert.equal(sourcesHref(document), SOURCES_PATH);
});

test('a later hashchange re-applies a lens-shaped change', async () => {
  const document = await wire(GUIDE_URL);
  assert.equal(document.documentElement.classList.contains('lens-personalized'), false);

  window.location.hash = `#${lensFragment(['strn'])}`;
  window.dispatchEvent(new Event('hashchange'));
  assert.equal(document.documentElement.classList.contains('lens-personalized'), true);
});

// Clicking around the page must never manufacture a load-time explanation.
test('a later hashchange to an ordinary anchor changes no selection', async () => {
  const document = await wire(`${GUIDE_URL}#${lensFragment(['strn'])}`);
  window.location.hash = '#guide-races';
  window.dispatchEvent(new Event('hashchange'));

  assert.equal(document.documentElement.classList.contains('lens-personalized'), true);
  assert.equal(notice(document).hidden, true);
});

test('the module keeps client state out of storage', () => {
  assertModuleGuard('guide-client.mjs');
});
