import assert from 'node:assert/strict';
import test from 'node:test';

import { DEFAULT_POST_LOGIN_HASH, resolvePostLoginNavigation } from './sessionNavigation.js';

test('resolvePostLoginNavigation soft-finalizes when target hash matches current location', () => {
  assert.deepEqual(
    resolvePostLoginNavigation(DEFAULT_POST_LOGIN_HASH, {
      pathname: '/',
      search: '',
      hash: '#/'
    }),
    { action: 'reload' }
  );
});

test('resolvePostLoginNavigation navigates when target hash differs', () => {
  assert.deepEqual(
    resolvePostLoginNavigation('#/admin', {
      pathname: '/',
      search: '',
      hash: '#/'
    }),
    { action: 'navigate', url: '/#/admin' }
  );
});

test('resolvePostLoginNavigation accepts hashless redirect paths', () => {
  assert.deepEqual(
    resolvePostLoginNavigation('/tickets/new', {
      pathname: '/app/',
      search: '?x=1',
      hash: '#/'
    }),
    { action: 'navigate', url: '/app/?x=1#/tickets/new' }
  );
});
