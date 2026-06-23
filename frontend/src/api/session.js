import {
  SESSION_CHANGE_EVENT,
  SESSION_FINALIZED_EVENT,
  currentUser,
  invalidateSessionCaches,
  saveSession
} from './client.js';
import { DEFAULT_POST_LOGIN_HASH, resolvePostLoginNavigation } from './sessionNavigation.js';

export { DEFAULT_POST_LOGIN_HASH, resolvePostLoginNavigation } from './sessionNavigation.js';

function dispatchSessionFinalized(user) {
  window.dispatchEvent(new CustomEvent(SESSION_FINALIZED_EVENT, { detail: { user } }));
}

function canSoftFinalizeSession(user) {
  if (!user || typeof user !== 'object') return false;
  if (!user.kind) return false;
  return true;
}

export function finalizeSession(payload, { redirectTo = DEFAULT_POST_LOGIN_HASH } = {}) {
  saveSession(payload);
  invalidateSessionCaches();

  const navigation = resolvePostLoginNavigation(redirectTo, {
    pathname: window.location.pathname,
    search: window.location.search,
    hash: window.location.hash
  });

  if (navigation.action === 'navigate') {
    window.location.replace(navigation.url);
    return;
  }

  if (canSoftFinalizeSession(payload.user)) {
    dispatchSessionFinalized(payload.user);
    return;
  }

  window.location.reload();
}

export function applySessionUser(user) {
  if (user) {
    localStorage.setItem('ticketmaster.user', JSON.stringify(user));
  }
  invalidateSessionCaches();
  dispatchSessionFinalized(user);
}

export function readStoredSessionUser() {
  return currentUser();
}
