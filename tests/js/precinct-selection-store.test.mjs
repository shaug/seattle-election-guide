import assert from 'node:assert/strict';
import test from 'node:test';
import {
  clearPrecinct,
  loadPrecinct,
  savePrecinct,
} from '../../src/election_guide/rendering/templates/precinct-selection-store.mjs';
import { installDom } from './support/dom.mjs';
import { assertModuleGuard } from './support/module-guards.mjs';

test('memory stores only a general-election precinct and clears it', () => {
  installDom();
  assert.equal(loadPrecinct('wa-2026-general'), null);
  assert.equal(savePrecinct('wa-2026-general', '1279'), true);
  assert.equal(loadPrecinct('wa-2026-general'), '1279');
  assert.equal(loadPrecinct('wa-2026-primary'), null);
  assert.equal(clearPrecinct('wa-2026-general'), true);
  assert.equal(loadPrecinct('wa-2026-general'), null);
});
test('blocked memory never prevents URL-only use', () => {
  installDom();
  Object.defineProperty(window, 'localStorage', {
    get() {
      throw Error('blocked');
    },
  });
  assert.equal(loadPrecinct('wa-2026-general'), null);
  assert.equal(savePrecinct('wa-2026-general', '1279'), false);
  assert.equal(clearPrecinct('wa-2026-general'), false);
});
test('memory owner obeys its narrow capability guard', () =>
  assertModuleGuard('precinct-selection-store.mjs'));

test('Primary memory requires an admitted literal-ID allowlist and rejects address/free/unknown/cross-election text', () => {
  installDom();
  const names = new Set(['SEA 46-1279', 'SEA 36-1273']);
  for (const invalid of ['600 4th Ave', 'free text', 'SEA 99-9999', '1279']) {
    assert.equal(savePrecinct('wa-2026-primary', invalid, names), false);
  }
  assert.equal(savePrecinct('wa-2026-primary', 'SEA 46-1279'), false);
  assert.equal(savePrecinct('wa-2026-primary', 'SEA 46-1279', names), true);
  assert.equal(loadPrecinct('wa-2026-primary', names), 'SEA 46-1279');
  assert.equal(loadPrecinct('wa-2026-primary'), null);
  assert.equal(loadPrecinct('wa-2026-general'), null);
  window.localStorage.setItem('seg-precinct-v1:wa-2026-primary', '600 4th Ave');
  assert.equal(loadPrecinct('wa-2026-primary', names), null);
  assert.equal(clearPrecinct('wa-2026-primary'), true);
});
