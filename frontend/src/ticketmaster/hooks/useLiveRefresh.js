import { useEffect, useRef } from 'react';

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
