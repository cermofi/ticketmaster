import {
  SESSION_FINALIZED_EVENT,
  currentUser,
  getReturnToken,
  hasReturnToAdmin,
  saveSession
} from './client.js';
import { invalidateForTransition, SESSION_TRANSITIONS } from './queryStore.js';
import { DEFAULT_POST_LOGIN_HASH, resolvePostLoginNavigation } from './sessionNavigation.js';

export { DEFAULT_POST_LOGIN_HASH, resolvePostLoginNavigation } from './sessionNavigation.js';
export { DATA_DOMAINS, INVALIDATION_MAP, SESSION_TRANSITIONS } from './queryStore.js';

function dispatchSessionFinalized(user) {
  window.dispatchEvent(new CustomEvent(SESSION_FINALIZED_EVENT, { detail: { user } }));
}

function canSoftFinalizeSession(user) {
  if (!user || typeof user !== 'object') return false;
  if (!user.kind) return false;
  return true;
}

function resolveSessionTransition(payload, { beforeReturnToken = false } = {}) {
  if (payload?.return_token) {
    return SESSION_TRANSITIONS.impersonationStart;
  }
  if (beforeReturnToken && !payload?.return_token) {
    return SESSION_TRANSITIONS.impersonationEnd;
  }
  return SESSION_TRANSITIONS.login;
}

export function finalizeSession(payload, { redirectTo = DEFAULT_POST_LOGIN_HASH, transition } = {}) {
  const hadReturnToken = hasReturnToAdmin();
  saveSession(payload);
  const resolved = transition ?? resolveSessionTransition(payload, { beforeReturnToken: hadReturnToken });
  invalidateForTransition(resolved);

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
  invalidateForTransition(SESSION_TRANSITIONS.sessionRefresh);
  dispatchSessionFinalized(user);
}

export function logoutSession() {
  localStorage.removeItem('ticketmaster.token');
  localStorage.removeItem('ticketmaster.user');
  localStorage.removeItem('ticketmaster.return_token');
  invalidateForTransition(SESSION_TRANSITIONS.logout);
}

export function readStoredSessionUser() {
  return currentUser();
}
