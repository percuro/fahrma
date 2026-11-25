/**
 * What the forms need without a connection – the account, the group with its members, the
 * cars and the recent trips – is kept on this device and restored when the app starts. Balances
 * and settlements are never kept: amounts of money always come fresh from the server.
 */
import type { QueryClient, QueryKey } from '@tanstack/react-query';
import type { Me } from './types';

export const CACHE_KEY = 'fahrma:cache';
const VERSION = 1;
const GROUP_PATHS = new Set(['', '/cars', '/trips']);

interface Saved {
  v: number;
  queries: { key: QueryKey; data: unknown; updatedAt: number }[];
}

export function isKept(key: QueryKey): boolean {
  if (key.length === 1 && key[0] === 'me') return true;
  return key.length === 3 && key[0] === 'group' && typeof key[2] === 'string' && GROUP_PATHS.has(key[2]);
}

function storage(): Storage | null {
  try {
    return globalThis.localStorage ?? null;
  } catch {
    return null;
  }
}

/** Before the first render: the last known state, refreshed by the queries as usual. */
export function restoreCache(queryClient: QueryClient): void {
  try {
    const raw = storage()?.getItem(CACHE_KEY);
    if (!raw) return;
    const saved = JSON.parse(raw) as Saved;
    if (saved.v !== VERSION) return;
    for (const { key, data, updatedAt } of saved.queries) {
      if (isKept(key)) queryClient.setQueryData(key, data, { updatedAt });
    }
  } catch {
    // A broken cache only means a normal start
  }
}

export function clearCache(): void {
  try {
    storage()?.removeItem(CACHE_KEY);
  } catch {
    // nothing to remove
  }
}

/** Keep the cache up to date; returns the unsubscribe function. */
export function persistCache(queryClient: QueryClient): () => void {
  let timer: ReturnType<typeof setTimeout> | undefined;
  let userId = queryClient.getQueryData<Me | null>(['me'])?.id ?? null;

  const save = () => {
    timer = undefined;
    // Logged out or session expired: keep what is there (the same person logs in again),
    // logging out removes it explicitly
    if (!queryClient.getQueryData<Me | null>(['me'])) return;
    // Also queries whose last refresh failed (offline): their data is still the last known state
    const queries = queryClient
      .getQueryCache()
      .getAll()
      .filter((query) => query.state.data !== undefined && isKept(query.queryKey))
      .map((query) => ({ key: query.queryKey, data: query.state.data, updatedAt: query.state.dataUpdatedAt }));
    try {
      storage()?.setItem(CACHE_KEY, JSON.stringify({ v: VERSION, queries } satisfies Saved));
    } catch {
      // Storage full or blocked: the app works, only not offline
    }
  };

  return queryClient.getQueryCache().subscribe((event) => {
    if (event.type !== 'updated' || event.action.type !== 'success' || !isKept(event.query.queryKey)) return;
    if (event.query.queryKey[0] === 'me') {
      const id = (event.query.state.data as Me | null | undefined)?.id ?? null;
      // Someone else logged in on this device: nothing of the previous person stays
      if (id !== null && userId !== null && id !== userId) queryClient.removeQueries({ queryKey: ['group'] });
      if (id !== null) userId = id;
    }
    timer ??= setTimeout(save, 500);
  });
}
