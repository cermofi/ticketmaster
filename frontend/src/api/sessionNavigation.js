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
