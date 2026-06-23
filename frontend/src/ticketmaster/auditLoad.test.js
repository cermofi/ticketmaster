import assert from 'node:assert/strict';
import test from 'node:test';

import { shouldShowAuditInitialLoading } from './auditLoad.js';

test('shouldShowAuditInitialLoading shows spinner only before first load completes', () => {
  assert.equal(shouldShowAuditInitialLoading(true, false), true);
  assert.equal(shouldShowAuditInitialLoading(false, false), false);
  assert.equal(shouldShowAuditInitialLoading(true, true), false);
  assert.equal(shouldShowAuditInitialLoading(false, true), false);
});
