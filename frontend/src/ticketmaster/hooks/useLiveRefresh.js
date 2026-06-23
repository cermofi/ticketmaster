import { useEffect, useRef } from 'react';

import { SESSION_CHANGE_EVENT } from '../../api/client.js';
import { DATA_DOMAINS, registerDomainInvalidator } from '../../api/queryStore.js';

export function useRefetchOnFocus(refetch, enabled = true) {
  const refetchRef = useRef(refetch);
  refetchRef.current = refetch;

  useEffect(() => {
    if (!enabled) return undefined;

    const handleRefresh = () => {
      if (document.visibilityState !== 'visible') return;
      refetchRef.current();
    };

    window.addEventListener('focus', handleRefresh);
    document.addEventListener('visibilitychange', handleRefresh);
    return () => {
      window.removeEventListener('focus', handleRefresh);
      document.removeEventListener('visibilitychange', handleRefresh);
    };
  }, [enabled]);
}

export function useRefetchOnSessionChange(refetch, enabled = true) {
  const refetchRef = useRef(refetch);
  refetchRef.current = refetch;

  useEffect(() => {
    if (!enabled) return undefined;

    const handleSessionChange = () => {
      refetchRef.current();
    };

    window.addEventListener(SESSION_CHANGE_EVENT, handleSessionChange);
    return () => window.removeEventListener(SESSION_CHANGE_EVENT, handleSessionChange);
  }, [enabled]);
}

/**
 * Register screen refetch with centralized query store domains and listen for session changes.
 * @param {string|string[]} domains - DATA_DOMAINS value(s) this screen owns
 * @param {Function} refetch
 * @param {boolean} enabled
 */
export function useSessionDomainRefresh(domains, refetch, enabled = true) {
  const refetchRef = useRef(refetch);
  refetchRef.current = refetch;
  const domainList = Array.isArray(domains) ? domains : [domains];

  useEffect(() => {
    if (!enabled) return undefined;
    const unsubs = domainList.map((domain) =>
      registerDomainInvalidator(domain, () => refetchRef.current())
    );
    return () => unsubs.forEach((unsub) => unsub());
  }, [enabled, ...domainList]);

  useRefetchOnSessionChange(refetch, enabled);
}

export { DATA_DOMAINS };

export function usePolling(refetch, intervalMs, enabled = true) {
  const refetchRef = useRef(refetch);
  refetchRef.current = refetch;

  useEffect(() => {
    if (!enabled || !intervalMs) return undefined;

    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') {
        refetchRef.current();
      }
    }, intervalMs);

    return () => window.clearInterval(timer);
  }, [enabled, intervalMs]);
}
