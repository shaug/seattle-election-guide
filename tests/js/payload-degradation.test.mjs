// A refused schema must leave the real audited page usable and tell the reader
// why personalization is unavailable (docs/FRONTEND.md § The data contract).
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { installDom } from './support/dom.mjs';

installDom();
const { PAYLOAD_NOTICE, readClientPayload, requireClientPayload } = await import(
  '../../src/election_guide/rendering/templates/client-payload.mjs'
);

for (const text of [null, '{ broken json', '{}', '{"schema_version":"2.0"}']) {
  test(`a refused payload (${text}) reveals the notice before bootstrap stops`, () => {
    const document = installDom();
    document.body.innerHTML =
      '<p data-payload-notice hidden></p><main><p>Audited results</p></main>';
    if (text !== null) {
      const element = document.createElement('script');
      element.type = 'application/json';
      element.setAttribute('data-client-payload', '');
      element.textContent = text;
      document.body.append(element);
    }
    const notice = document.querySelector('[data-payload-notice]');
    const baseline = document.querySelector('main').firstElementChild;
    assert.equal(readClientPayload(document), null);
    assert.equal(notice.hidden, false);
    assert.equal(notice.textContent, PAYLOAD_NOTICE);
    assert.throws(() => requireClientPayload(document), /unusable client payload/);
    assert.equal(document.querySelector('main').firstElementChild, baseline);
    assert.equal(baseline.textContent, 'Audited results');
  });
}

for (const [page, fixture, selector, throws] of [
  ['guide', 'guide-audited-page.html', '[data-lens-result]', true],
  ['sources', 'sources-audited-page.html', '[data-sources-tree]', true],
  ['race', 'race-audited-page-ld-32-state-representative-1.html', '[data-race-candidates]', true],
  ['compare', 'compare-audited-page.html', '[data-comparison-table]', false],
]) {
  const { boot } = await import(`../../src/election_guide/rendering/templates/${page}-entry.mjs`);
  const html = readFileSync(new URL(`./fixtures/${fixture}`, import.meta.url), 'utf8');
  test(`${page} boot preserves its audited region when the schema is unsupported`, () => {
    const document = installDom();
    document.write(html);
    const element = document.querySelector('[data-client-payload]');
    assert.ok(element, 'the real page fixture must carry its payload');
    const payload = JSON.parse(element.textContent);
    payload.schema_version = '2.0';
    element.textContent = JSON.stringify(payload);
    const region = document.querySelector(selector);
    assert.ok(region, 'the real page fixture must carry its audited region');
    const children = [...region.childNodes];
    const markup = region.innerHTML;
    const notice = document.querySelector('[data-payload-notice]');
    assert.equal(notice.hidden, true);

    if (throws) assert.throws(boot, /unusable client payload/);
    else assert.doesNotThrow(boot);

    assert.equal(document.querySelector(selector), region);
    assert.equal(region.childNodes.length, children.length);
    for (const [index, child] of [...region.childNodes].entries()) {
      assert.equal(child, children[index]);
    }
    assert.equal(region.innerHTML, markup);
    assert.equal(document.querySelector('[data-payload-notice]'), notice);
    assert.equal(notice.hidden, false);
    assert.equal(notice.textContent, PAYLOAD_NOTICE);
  });
}
