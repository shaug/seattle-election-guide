// The markup-parity check docs/FRONTEND.md § Rendering calls for, applied to a
// race page's four lens regions (issue #136), on the harness issue #238 built.
//
// Every claim is made against real server output — `tests/page_parity.py`
// renders the pages and commits them — rather than against hand-written markup,
// because the rule is about what the Jinja template actually produces.
//
// Which pages are committed is derived rather than chosen: a race page is
// ~60KB stripped, so one per race would be two megabytes of fixture for a
// comparison that needs each *shape* once. `race_parity_fixture_ids` takes the
// fewest races that show every reachable branch of the markup, and
// `tests/test_rendering.py` fails when the committed files are not that set.
// The four branches the published ballot cannot reach — an Insufficient grade,
// an absent share, a low fill, and an unverified cell — are covered by the
// hand-built view models in `race-detail.test.mjs`.

import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import { installDom } from './support/dom.mjs';
import { assertMarkupParity } from './support/markup-parity.mjs';

const FIXTURE_DIR = fileURLToPath(new URL('./fixtures/', import.meta.url));
const CANONICAL = /<link rel="canonical" href="([^"]+)">/;
const DOCUMENT_SHELL = /^[\s\S]*?<html[^>]*>|<\/html>[\s\S]*$/g;

const REGIONS = [
  '[data-lens-result]',
  '[data-lens-context]',
  '[data-lens-foot]',
  '[data-race-candidates]',
];

/** Every committed race page, in a stable order. */
const FIXTURES = readdirSync(FIXTURE_DIR)
  .filter((name) => name.startsWith('race-audited-page-') && name.endsWith('.html'))
  .sort()
  .map((name) => {
    const html = readFileSync(`${FIXTURE_DIR}${name}`, 'utf8');
    const canonical = CANONICAL.exec(html);
    assert.ok(canonical, `${name} carries no canonical URL to resolve its links against`);
    return { name, html, url: canonical[1] };
  });

assert.ok(FIXTURES.length > 0, 'no committed race page fixtures; run tests/page_parity.py');

// The DOM first, then lit-html and anything that reaches it: see dom.mjs. One
// window for the whole file — each fixture replaces the document's contents
// rather than installing a second DOM, because lit-html binds its document once
// per process and a second window would leave it rendering into the first.
const document = installDom(FIXTURES[0].url);
const { wireRacePage } = await import(
  '../../src/election_guide/rendering/templates/race-client.mjs'
);
const { readClientPayload } = await import(
  '../../src/election_guide/rendering/templates/client-payload.mjs'
);

/**
 * A detached copy of one region's children, so the server's markup survives the
 * render that replaces it.
 *
 * @param {Element} region
 */
function detachedCopy(region) {
  const container = document.createElement('div');
  for (const child of [...region.childNodes]) container.append(child.cloneNode(true));
  return container;
}

/**
 * A same-version selection fragment naming exactly `codes`.
 *
 * @param {RacePayload} payload
 * @param {readonly string[]} codes
 */
const selectionFragment = (payload, codes) =>
  `#lens=2&mode=s&panel=${payload.panel_id}&ph=${payload.panel_hash.slice(0, 12)}` +
  `&data=${payload.data_version}&scoring=${payload.scoring.configuration_id}` +
  `&sel=${codes.join('')}`;

for (const fixture of FIXTURES) {
  test(`${fixture.name}: the audited default is left exactly as the server rendered it, and the restore reproduces it`, () => {
    document.documentElement.innerHTML = fixture.html.replace(DOCUMENT_SHELL, '');
    window.location.hash = '';

    const payload = /** @type {RacePayload} */ (readClientPayload(document));
    assert.ok(payload, `${fixture.name} carries no readable payload`);

    /** @type {Map<string, Element>} */
    const audited = new Map();
    for (const selector of REGIONS) {
      const region = document.querySelector(selector);
      assert.ok(region, `${fixture.name} has no ${selector} region`);
      audited.set(selector, detachedCopy(region));
    }
    const firstCandidate = document.querySelector('[data-race-candidates]').firstElementChild;
    const summary = document.querySelector('[data-race-detail-summary]');
    const auditedSummary = summary.textContent;

    wireRacePage(payload);

    // The takeover idiom: a region whose content is a projection of state does
    // no DOM work at all until the state leaves the audited default.
    assert.ok(
      document.querySelector('[data-race-candidates]').firstElementChild === firstCandidate,
      'the client rebuilt the candidate region at the audited default. The server renders the ' +
        'complete audited baseline and the default view does no DOM work on it ' +
        '(rule: rendering, docs/FRONTEND.md).',
    );
    // The summary is referenced by aria-describedby, so its element is the
    // server's for the life of the page — lit only ever writes its text.
    assert.ok(document.querySelector('[data-race-detail-summary]') === summary);
    assert.equal(summary.textContent, auditedSummary);

    const codes = payload.sources
      .filter((source) => source.panel_role !== 'comparison' && source.selectable)
      .map((source) => source.code);
    assert.ok(codes.length > 1, `${fixture.name} publishes too few tallying sources`);

    /** @param {string} fragment */
    const goTo = (fragment) => {
      window.location.hash = fragment;
      window.dispatchEvent(new Event('hashchange'));
    };

    goTo(selectionFragment(payload, codes.slice(1)));
    assert.ok(
      document.querySelector('[data-race-candidates]').firstElementChild !== firstCandidate,
      'a divergent selection should have taken the regions over from the server',
    );

    // Back to the audited default. A link naming every tallying source is what
    // the reader gets from the sources page's Reset, and is the only thing that
    // clears a lens: an absent fragment carries no selection to apply.
    goTo(selectionFragment(payload, codes));

    for (const selector of REGIONS) {
      const region = document.querySelector(selector);
      assert.ok(region);
      assertMarkupParity({
        region: `${fixture.name}'s ${selector} region`,
        client: region,
        server: /** @type {Element} */ (audited.get(selector)),
        base: fixture.url,
      });
    }
    assert.equal(
      document.querySelector('[data-race-detail-summary]').textContent,
      auditedSummary,
      'clearing the lens must restore the audited summary the payload publishes',
    );
  });
}
