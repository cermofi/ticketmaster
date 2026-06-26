import assert from 'node:assert/strict';
import test from 'node:test';

import { isLoginFormSubmittable, loginSubmitLabel, normalizeLoginIdentifier, resolveLoginErrorMessage } from './loginFlow.js';
import { availableNewTicketModes, isNewTicketModeVisible, resolveNewTicketInitialMode } from './newTicketMode.js';
import { canReturnToAdmin, canSignInAsPartner } from './sessionControls.js';

test('normalizeLoginIdentifier trims whitespace', () => {
  assert.equal(normalizeLoginIdentifier('  admin@example.test  '), 'admin@example.test');
});

test('isLoginFormSubmittable requires credentials and blocks while submitting', () => {
  assert.equal(isLoginFormSubmittable({ identifier: 'a@b.cz', password: 'secret', activationToken: '', submitting: false }), true);
  assert.equal(isLoginFormSubmittable({ identifier: '', password: 'secret', activationToken: '', submitting: false }), false);
  assert.equal(isLoginFormSubmittable({ identifier: 'a@b.cz', password: 'secret', activationToken: '', submitting: true }), false);
});

test('loginSubmitLabel switches for activation flow', () => {
  assert.equal(loginSubmitLabel(''), 'Sign in');
  assert.equal(loginSubmitLabel('token-123'), 'Set password');
});

test('resolveLoginErrorMessage prefers unified API message', () => {
  assert.equal(resolveLoginErrorMessage({ response: { data: { message: 'Invalid e-mail or password' } } }), 'Invalid e-mail or password');
  assert.equal(resolveLoginErrorMessage({ response: { data: { detail: 'Legacy detail' } } }), 'Legacy detail');
});

test('canSignInAsPartner is limited to Admin and Delivery Manager', () => {
  assert.equal(canSignInAsPartner({ kind: 'internal', internal_roles: ['Admin'] }), true);
  assert.equal(canSignInAsPartner({ kind: 'internal', internal_roles: ['L1'] }), false);
  assert.equal(canSignInAsPartner({ kind: 'partner', partner_role: 'responsible' }), false);
});

test('canReturnToAdmin requires partner session with return token', () => {
  assert.equal(canReturnToAdmin({ kind: 'partner' }, true), true);
  assert.equal(canReturnToAdmin({ kind: 'partner' }, false), false);
  assert.equal(canReturnToAdmin({ kind: 'internal', internal_roles: ['Admin'] }, true), false);
});

test('resolveNewTicketInitialMode respects internal/partner target', () => {
  assert.equal(resolveNewTicketInitialMode({ kind: 'internal' }, 'partner'), 'partner');
  assert.equal(resolveNewTicketInitialMode({ kind: 'internal' }, null), 'internal');
  assert.equal(resolveNewTicketInitialMode({ kind: 'partner' }, 'partner'), 'partner');
});

test('availableNewTicketModes exposes internal + partner only for internal users', () => {
  assert.deepEqual(availableNewTicketModes({ kind: 'internal' }), ['internal', 'partner']);
  assert.deepEqual(availableNewTicketModes({ kind: 'partner' }), ['partner']);
  assert.equal(isNewTicketModeVisible({ kind: 'partner' }, 'internal'), false);
  assert.equal(isNewTicketModeVisible({ kind: 'internal' }, 'partner'), true);
});
