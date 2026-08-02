// compare-table.mjs is the Comparisons table's markup. It is a computing
// module — it names no environment identifier and reads nothing out of the DOM
// — so it takes the purity tier of the shared guard, and its behavior is
// testable in the lightweight DOM rather than only in Chrome
// (docs/FRONTEND.md § Testing).
//
// The claim these tests exist for is the one the imperative renderer could not
// make: a re-render preserves the elements it did not change, so a control the
// reader is using is still the same element afterwards, still focused, with
// nothing put back.
//
// Element identity is asserted with `assert.ok(a === b)` rather than
// `assert.equal(a, b)` throughout. A failing `assert.equal` would try to
// serialize two DOM nodes into its message, and a happy-dom node's object
// graph is large and circular enough to take the process down before the
// failure is ever printed.

import assert from 'node:assert/strict';
import test from 'node:test';
import { installDom } from './support/dom.mjs';
import { assertModuleGuard } from './support/module-guards.mjs';

// The DOM first, then lit-html and anything that reaches it: see dom.mjs.
const document = installDom();
const { render } = await import('lit-html');
const { comparisonBodyTemplate, comparisonHeadTemplate } = await import(
  '../../src/election_guide/rendering/templates/compare-table.mjs'
);

/**
 * A table in the document, because focus is only observable for an element
 * that is actually in one.
 *
 * @returns {{ table: HTMLTableElement, head: HTMLElement }}
 */
function freshTable() {
  document.body.replaceChildren();
  const table = /** @type {HTMLTableElement} */ (document.createElement('table'));
  const head = document.createElement('thead');
  table.append(head);
  document.body.append(table);
  return { table, head };
}

/**
 * @param {string[]} signals
 * @param {number|null} editing
 * @returns {import('../../src/election_guide/rendering/templates/compare-table.mjs').ComparisonHeadView}
 */
function headView(signals, editing = null) {
  return {
    columns: signals.map((signal, index) => ({
      signal,
      index,
      title: signal.toUpperCase(),
      controlLabel: `Change ${signal}`,
      editing: editing === index,
      groups:
        editing === index
          ? [
              {
                label: 'Published result',
                options: [
                  { value: 'gall', label: 'All sources', selected: false, disabled: false },
                  { value: signal, label: signal, selected: true, disabled: false },
                ],
              },
            ]
          : [],
      removeLabel: signals.length > 2 ? `Remove ${signal}` : null,
      canAdd: index === signals.length - 1 && signals.length < 3,
    })),
  };
}

const noActions = {
  onEdit() {},
  onChoose() {},
  onCancel() {},
  onDismiss() {},
  onRemove() {},
  onAdd() {},
};

/**
 * @param {string[]} raceIds
 * @returns {import('../../src/election_guide/rendering/templates/compare-table.mjs').ComparisonBodyView}
 */
function bodyView(raceIds) {
  return {
    columnCount: 1,
    empty: null,
    sections: [
      {
        sectionId: 'city',
        sectionLabel: 'City',
        rows: raceIds.map((raceId) => ({
          raceId,
          raceLabel: raceId,
          raceHref: `../#race-${raceId}`,
          differs: false,
          cells: [
            {
              signal: 'gall',
              columnLabel: 'All sources',
              kind: 'baseline',
              agreement: 'reference',
              leadingPickIds: [`${raceId}--a`],
              share: '1',
              explicitSourceCount: 3,
              choiceLabels: ['A'],
              meta: '100% · 3 sources',
            },
          ],
        })),
      },
    ],
  };
}

test('the module computes markup and reaches for nothing', () => {
  assertModuleGuard('compare-table.mjs');
});

test('a control the reader is using survives the render its own change triggered', () => {
  const { head } = freshTable();
  render(comparisonHeadTemplate(headView(['gall', 'strn', 'stim']), noActions), head);

  const strnTitle = /** @type {HTMLElement|null} */ (
    head.querySelector('[data-comparison-title="1"]')
  );
  assert.ok(strnTitle, 'expected a title control for the second column');
  strnTitle.focus();
  assert.ok(document.activeElement === strnTitle, 'the control did not take focus');

  // The reader changes the third column. The second column's control is not
  // part of that change, so nothing about it should be rebuilt.
  render(comparisonHeadTemplate(headView(['gall', 'strn', 'Glab']), noActions), head);

  assert.ok(
    head.querySelector('[data-comparison-title="1"]') === strnTitle,
    'the untouched column was rebuilt; keyed rendering is what preserves it',
  );
  assert.ok(
    document.activeElement === strnTitle,
    'focus did not survive the render by identity, so something would have to restore it',
  );
  assert.equal(head.querySelector('[data-comparison-title="2"]')?.textContent, 'GLAB');
});

test('the picker replaces the title without disturbing the column beside it', () => {
  const { head } = freshTable();
  render(comparisonHeadTemplate(headView(['gall', 'strn', 'stim']), noActions), head);
  const neighbour = /** @type {HTMLElement|null} */ (
    head.querySelector('[data-comparison-title="2"]')
  );
  assert.ok(neighbour);
  neighbour.focus();

  render(comparisonHeadTemplate(headView(['gall', 'strn', 'stim'], 1), noActions), head);

  assert.equal(head.querySelector('[data-comparison-title="1"]'), null);
  assert.ok(head.querySelector('[data-comparison-column="1"]'), 'expected the picker to open');
  assert.ok(
    head.querySelector('[data-comparison-title="2"]') === neighbour,
    "opening one column's picker rebuilt another column",
  );
  assert.ok(document.activeElement === neighbour, 'focus left a control that did not change');
});

test('a row that survives a filter change is the same row', () => {
  const { table } = freshTable();
  render(
    comparisonBodyTemplate(bodyView(['one', 'two', 'three']), () => {}),
    table,
  );
  const second = table.querySelector('[data-comparison-race="two"]');
  assert.ok(second);

  render(
    comparisonBodyTemplate(bodyView(['two', 'three']), () => {}),
    table,
  );

  assert.ok(
    table.querySelector('[data-comparison-race="two"]') === second,
    'a surviving row was rebuilt; keyed rendering is what keeps the page steady under it',
  );
  assert.equal(table.querySelectorAll('[data-comparison-race]').length, 2);
});

test('a blank cell keeps the explanation the audited page carries', () => {
  const { table } = freshTable();
  render(
    comparisonBodyTemplate(
      {
        columnCount: 1,
        empty: null,
        sections: [
          {
            sectionId: 'city',
            sectionLabel: 'City',
            rows: [
              {
                raceId: 'mayor',
                raceLabel: 'Mayor',
                raceHref: '../#race-mayor',
                differs: false,
                cells: [
                  {
                    signal: 'stim',
                    columnLabel: 'The Seattle Times Editorial Board',
                    kind: 'blank',
                    agreement: 'neutral',
                    leadingPickIds: [],
                    share: null,
                    explicitSourceCount: null,
                    choiceLabels: [],
                    meta: null,
                  },
                ],
              },
            ],
          },
        ],
      },
      () => {},
    ),
    table,
  );

  const cell = table.querySelector('.comparison-cell');
  assert.ok(cell);
  assert.equal(cell.getAttribute('data-leading-pick-ids'), '[]');
  assert.equal(cell.hasAttribute('data-share'), false);
  assert.equal(cell.hasAttribute('data-explicit-source-count'), false);
  assert.equal(
    cell.querySelector('.comparison-cell-picks span')?.getAttribute('title'),
    'No endorsement published',
  );
  assert.equal(cell.querySelector('.comparison-cell-meta'), null);
});

test('the empty state offers the reset the filters need', () => {
  const { table } = freshTable();
  let reset = 0;
  render(
    comparisonBodyTemplate(
      {
        columnCount: 3,
        empty: { message: 'No races match the current filters.', action: 'Reset filters' },
        sections: [],
      },
      () => {
        reset += 1;
      },
    ),
    table,
  );

  const row = table.querySelector('.comparison-empty');
  assert.ok(row);
  assert.equal(row.querySelector('td')?.getAttribute('colspan'), '4');
  assert.equal(row.querySelector('p')?.textContent, 'No races match the current filters.');
  const button = /** @type {HTMLElement|null} */ (row.querySelector('.comparison-reset'));
  assert.ok(button);
  button.click();
  assert.equal(reset, 1);
});
