// sources-tree.mjs is the sources editor's selectable tree. A computing module
// — view model in, template out — so it takes the purity tier of the shared
// guard (docs/FRONTEND.md § Testing).
//
// Two claims the imperative version could not make, and one it could not even
// express:
//
//   identity      a re-render keeps every input element, so the checkbox a
//                 reader just pressed is still the one they are focused on
//                 (§ Rendering: a control the reader is using must still exist
//                 after the render it triggers);
//   both states   the checkbox's content attribute and its live property are
//                 both written, so a re-render can undo a click and the
//                 serialized markup still says what is counted;
//   indeterminate a partly-counted category, which has no content attribute at
//                 all and so cannot be server-rendered.

import assert from 'node:assert/strict';
import test from 'node:test';
import { installDom } from './support/dom.mjs';
import { assertModuleGuard } from './support/module-guards.mjs';

// The DOM first, then lit-html and anything that reaches it: see dom.mjs.
const document = installDom();
const { render } = await import('lit-html');
const { sourcesTreeTemplate } = await import(
  '../../src/election_guide/rendering/templates/sources-tree.mjs'
);

/** @type {{ source: [string, boolean][], category: [string, boolean][] }} */
let recorded = { source: [], category: [] };
const actions = {
  onSource: (/** @type {string} */ code, /** @type {boolean} */ checked) => {
    recorded.source.push([code, checked]);
  },
  onCategory: (/** @type {string} */ code, /** @type {boolean} */ checked) => {
    recorded.category.push([code, checked]);
  },
};

const host = document.createElement('div');
document.body.append(host);

/**
 * @param {readonly string[]} counted
 * @param {readonly string[]} [alsoIn]
 * @param {readonly string[]} [codes] Which sources the category holds, in order.
 *   Every test but the keyed-rendering one draws the same two; that one changes
 *   the list, which is the only way index reuse and keying differ.
 */
function draw(counted, alsoIn = [], codes = ['strn', 'urbn']) {
  const rows = codes.map((code) => ({
    code,
    name: code === 'strn' ? 'The Stranger' : 'The Urbanist',
    evidenceUrl: `https://example.test/${code}`,
    participation: '12 endorsements',
    alsoIn,
    checked: counted.includes(code),
  }));
  render(
    sourcesTreeTemplate(
      [
        {
          code: 'Gprs',
          label: 'Press',
          checked: counted.length === rows.length,
          indeterminate: counted.length > 0 && counted.length < rows.length,
          rows,
        },
      ],
      actions,
    ),
    host,
  );
  return host;
}

/** @param {string} code */
const box = (code) =>
  /** @type {HTMLInputElement} */ (host.querySelector(`[data-sources-source="${code}"]`));
const toggle = () =>
  /** @type {HTMLInputElement} */ (host.querySelector('[data-sources-category-toggle]'));

test('the audited default counts every source, in markup and in state', () => {
  draw(['strn', 'urbn']);

  assert.equal(box('strn').hasAttribute('checked'), true);
  assert.equal(box('strn').checked, true);
  assert.equal(toggle().checked, true);
  assert.equal(toggle().indeterminate, false);
  assert.equal(host.querySelector('.sources-count').textContent, '12 endorsements');
  assert.equal(
    host.querySelector('.sources-check a').getAttribute('href'),
    'https://example.test/strn',
  );
});

test('a re-render keeps the very same input elements', () => {
  draw(['strn', 'urbn']);
  const before = box('urbn');

  draw(['strn']);

  assert.ok(box('urbn') === before, 'the checkbox the reader is using was replaced');
  assert.equal(before.checked, false);
  assert.equal(before.hasAttribute('checked'), false);
  assert.equal(toggle().indeterminate, true);
  assert.equal(toggle().checked, false);
});

// The test above re-renders the same two rows in the same order, where index
// reuse and keying are indistinguishable — dropping `repeat` for `.map` passes
// it. Keying only shows itself when the list itself changes, so this drops the
// first row and asks whether the second one survived as the same element. With
// `repeat` keyed by code it does; with `.map` the reader's checkbox is the node
// that used to be the row above it, holding its state.
test('a row that outlives a change to the list is the same row', () => {
  draw(['strn', 'urbn']);
  const survivor = box('urbn');
  survivor.focus();

  draw(['urbn'], [], ['urbn']);

  assert.ok(
    box('urbn') === survivor,
    'the surviving row was rebuilt; keyed rendering is what preserves the control the ' +
      'reader is holding (rule: repeated lists use keyed rendering, docs/FRONTEND.md)',
  );
  assert.ok(
    document.activeElement === survivor,
    'focus did not survive the render by identity, so something would have to restore it',
  );
});

// The property, not only the attribute: a click sets the property, and only a
// property write can take it back.
test('a re-render undoes a click', () => {
  draw(['strn', 'urbn']);
  box('urbn').checked = false;

  draw(['strn', 'urbn']);

  assert.equal(box('urbn').checked, true);
});

test('a change on either control reports the code and the new state', () => {
  recorded = { source: [], category: [] };
  draw(['strn', 'urbn']);

  box('urbn').checked = false;
  box('urbn').dispatchEvent(new Event('change'));
  toggle().checked = false;
  toggle().dispatchEvent(new Event('change'));

  assert.deepEqual(recorded.source, [['urbn', false]]);
  assert.deepEqual(recorded.category, [['Gprs', false]]);
});

test('a source selectable elsewhere is tagged with the other categories', () => {
  draw(['strn', 'urbn'], ['Labor', 'Advocacy']);
  assert.equal(host.querySelector('.sources-also-in').textContent, 'also in: Labor, Advocacy');
});

test('a source in one category is tagged with nothing', () => {
  draw(['strn', 'urbn']);
  assert.equal(host.querySelector('.sources-also-in'), null);
});

test('the module keeps client state out of storage, and stays a computing module', () => {
  assertModuleGuard('sources-tree.mjs');
});
