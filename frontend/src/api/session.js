import { saveSession } from './client.js';
import { DEFAULT_POST_LOGIN_HASH, resolvePostLoginNavigation } from './sessionNavigation.js';

export { DEFAULT_POST_LOGIN_HASH, resolvePostLoginNavigation } from './sessionNavigation.js';

export function finalizeSession(payload, { redirectTo = DEFAULT_POST_LOGIN_HASH } = {}) {
  saveSession(payload);
  const navigation = resolvePostLoginNavigation(redirectTo, {
    pathname: window.location.pathname,
    search: window.location.search,
    hash: window.location.hash
  });
  if (navigation.action === 'reload') {
    window.location.reload();
    return;
  }
  window.location.replace(navigation.url);
}
