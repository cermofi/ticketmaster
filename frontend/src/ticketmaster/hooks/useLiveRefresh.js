import { useEffect, useRef } from 'react';

import { SESSION_CHANGE_EVENT } from '../../api/client.js';

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
