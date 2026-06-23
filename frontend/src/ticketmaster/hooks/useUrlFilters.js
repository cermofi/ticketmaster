import { useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router';

export function readUrlFilters(emptyFilters, keys, searchParams, { booleanKeys = [] } = {}) {
  const next = { ...emptyFilters };
  for (const key of keys) {
    const raw = searchParams.get(key);
    if (raw === null || raw === '') continue;
    if (booleanKeys.includes(key)) {
      next[key] = raw === 'true' || raw === '1';
    } else {
      next[key] = raw;
    }
  }
  return next;
}

export function writeUrlFilters(filters, keys, searchParams, { booleanKeys = [] } = {}) {
  const next = new URLSearchParams(searchParams);
  for (const key of keys) {
    const value = filters[key];
    if (booleanKeys.includes(key)) {
      if (value) next.set(key, 'true');
      else next.delete(key);
      continue;
    }
    if (value !== '' && value !== null && value !== undefined) next.set(key, String(value));
    else next.delete(key);
  }
  return next;
}

export function useUrlFilters(emptyFilters, keys, { booleanKeys = [] } = {}) {
  const [searchParams, setSearchParams] = useSearchParams();

  const filters = useMemo(
    () => readUrlFilters(emptyFilters, keys, searchParams, { booleanKeys }),
    [emptyFilters, keys, searchParams, booleanKeys],
  );

  const syncFiltersToUrl = useCallback((nextFilters, { replace = true } = {}) => {
    const nextParams = writeUrlFilters(nextFilters, keys, searchParams, { booleanKeys });
    setSearchParams(nextParams, { replace });
  }, [booleanKeys, keys, searchParams, setSearchParams]);

  const resetFilters = useCallback(() => {
    const nextParams = new URLSearchParams(searchParams);
    for (const key of keys) nextParams.delete(key);
    setSearchParams(nextParams, { replace: true });
    return { ...emptyFilters };
  }, [emptyFilters, keys, searchParams, setSearchParams]);

  return { filters, syncFiltersToUrl, resetFilters, searchParams };
}
