import { saveSession } from './client.js';

export const DEFAULT_POST_LOGIN_HASH = '#/';

export function resolvePostLoginNavigation(redirectTo, location = {}) {
  const { pathname = '/', search = '', hash = '' } = location;
  const normalizedHash = redirectTo.startsWith('#')
    ? redirectTo
    : `#${redirectTo.replace(/^\/?/, '/')}`;
  const nextUrl = `${pathname}${search}${normalizedHash}`;
  const currentUrl = `${pathname}${search}${hash || ''}`;
  if (nextUrl === currentUrl) {
    return { action: 'reload' };
  }
  return { action: 'navigate', url: nextUrl };
}

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
