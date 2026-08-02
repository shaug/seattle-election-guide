// The markup-parity harness (docs/FRONTEND.md § Rendering).
//
// The rule it enforces: a lit-html template rendered with audited view-model
// data must produce the region the Jinja template rendered. Both sides are
// parsed and reduced to the same canonical form, so the comparison is of
// markup, not of the incidental text each generator emits around it.
//
// What canonicalisation deliberately ignores, and why each is not a difference
// a reader could see:
//
//   comments       lit leaves its part markers in the DOM as comment nodes.
//   whitespace     Jinja indents its output; runs of whitespace collapse, and
//                  a run that separates nothing is dropped.
//   attribute order  attributes are a set, not a sequence.
//   href form      resolved against the page URL before comparing, so the
//                  server's absolute path and a client's relative one are the
//                  same link rather than a false difference.
//
// Everything else — tag names, nesting, every attribute name and value, and
// all text — must match exactly. The comparer takes a region rather than a
// page so that issue #248 can bring the guide and sources lens regions to it
// without changing anything here.

import assert from 'node:assert/strict';

/** Attributes whose value is a URL, and so is compared after resolution. */
const URL_ATTRIBUTES = new Set(['href', 'src']);

/**
 * @typedef {object} CanonicalElement
 * @property {'element'} type
 * @property {string} tag
 * @property {[string, string][]} attributes
 * @property {CanonicalNode[]} children
 */

/**
 * @typedef {object} CanonicalText
 * @property {'text'} type
 * @property {string} text
 */

/** @typedef {CanonicalElement|CanonicalText} CanonicalNode */

/**
 * @param {Element} element
 * @param {string} base
 * @returns {[string, string][]}
 */
function canonicalAttributes(element, base) {
  return [...element.attributes]
    .map((attribute) => {
      const value = URL_ATTRIBUTES.has(attribute.name)
        ? new URL(attribute.value, base).href
        : attribute.value;
      return /** @type {[string, string]} */ ([attribute.name, value]);
    })
    .sort(([left], [right]) => (left < right ? -1 : left > right ? 1 : 0));
}

/**
 * Reduce one region's children to the form the two renderings must share.
 *
 * Text is collapsed and then merged across the comment markers lit leaves
 * between its parts, so one run of text compares as one run however many nodes
 * each renderer split it into. A run that is only whitespace is dropped: it is
 * the Jinja template's indentation, and it separates nothing a reader sees.
 *
 * @param {Node} region The element whose children are the region.
 * @param {string} base The address relative URLs resolve against.
 * @returns {CanonicalNode[]}
 */
export function canonicalRegion(region, base) {
  /** @type {CanonicalNode[]} */
  const children = [];
  for (const child of region.childNodes) {
    // Node.COMMENT_NODE
    if (child.nodeType === 8) continue;
    // Node.TEXT_NODE
    if (child.nodeType === 3) {
      const text = (child.textContent ?? '').replace(/\s+/g, ' ');
      const previous = children.at(-1);
      if (previous !== undefined && previous.type === 'text') previous.text += text;
      else children.push({ type: 'text', text });
      continue;
    }
    // Node.ELEMENT_NODE
    if (child.nodeType !== 1) continue;
    const element = /** @type {Element} */ (child);
    children.push({
      type: 'element',
      tag: element.tagName.toLowerCase(),
      attributes: canonicalAttributes(element, base),
      children: canonicalRegion(element, base),
    });
  }
  return children
    .map((child) => (child.type === 'text' ? { ...child, text: child.text.trim() } : child))
    .filter((child) => child.type !== 'text' || child.text !== '');
}

/**
 * A one-line-per-node rendering, so a mismatch reports where it is rather than
 * dumping two object graphs at the reader.
 *
 * @param {CanonicalNode[]} nodes
 * @param {string} [indent]
 * @returns {string[]}
 */
export function describeRegion(nodes, indent = '') {
  return nodes.flatMap((node) => {
    if (node.type === 'text') return [`${indent}"${node.text}"`];
    const attributes = node.attributes.map(([name, value]) => ` ${name}="${value}"`).join('');
    return [`${indent}<${node.tag}${attributes}>`, ...describeRegion(node.children, `${indent}  `)];
  });
}

/**
 * @param {CanonicalNode[]} left
 * @param {CanonicalNode[]} right
 * @returns {string|null} The first differing line, or null when they agree.
 */
function firstDifference(left, right) {
  const leftLines = describeRegion(left);
  const rightLines = describeRegion(right);
  for (let index = 0; index < Math.max(leftLines.length, rightLines.length); index += 1) {
    if (leftLines[index] === rightLines[index]) continue;
    return (
      `line ${index + 1} of the region:\n` +
      `  server: ${rightLines[index] ?? '(nothing — the server region ends here)'}\n` +
      `  lit:    ${leftLines[index] ?? '(nothing — the lit region ends here)'}`
    );
  }
  return null;
}

/**
 * Assert that a lit-rendered region is the region the server rendered.
 *
 * @param {object} options
 * @param {string} options.region A name for the region, used in failures.
 * @param {Node} options.client The container lit rendered into.
 * @param {Node} options.server The container holding the server's markup.
 * @param {string} options.base The address relative URLs resolve against.
 */
export function assertMarkupParity({ region, client, server, base }) {
  const rendered = canonicalRegion(client, base);
  const audited = canonicalRegion(server, base);
  const difference = firstDifference(rendered, audited);
  assert.equal(
    difference,
    null,
    `the lit-html rendering of ${region} is not the region the Jinja template rendered. ` +
      `Client and server markup for the same region must agree (rule: rendering, ` +
      `docs/FRONTEND.md); ${difference}`,
  );
}
