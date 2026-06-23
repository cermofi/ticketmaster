import assert from 'node:assert/strict';
import test from 'node:test';

import {
  DATA_DOMAINS,
  INVALIDATION_MAP,
  SESSION_TRANSITIONS,
  invalidateDomains,
  registerDomainInvalidator
} from './queryStore.js';

test('INVALIDATION_MAP covers all session transitions', () => {
  for (const transition of Object.values(SESSION_TRANSITIONS)) {
    assert.ok(Array.isArray(INVALIDATION_MAP[transition]), transition);
    assert.ok(INVALIDATION_MAP[transition].length > 0, transition);
  }
});

test('logout invalidates every data domain', () => {
  const domains = INVALIDATION_MAP[SESSION_TRANSITIONS.logout];
  for (const domain of Object.values(DATA_DOMAINS)) {
    assert.ok(domains.includes(domain), domain);
  }
});

test('invalidateDomains calls registered invalidators for matching domains', () => {
  let ticketsCalls = 0;
  let metaCalls = 0;
  const unregisterTickets = registerDomainInvalidator(DATA_DOMAINS.tickets, () => {
    ticketsCalls += 1;
  });
  const unregisterMeta = registerDomainInvalidator(DATA_DOMAINS.meta, () => {
    metaCalls += 1;
  });
  try {
    invalidateDomains([DATA_DOMAINS.tickets]);
    assert.equal(ticketsCalls, 1);
    assert.equal(metaCalls, 0);
  } finally {
    unregisterTickets();
    unregisterMeta();
  }
});
