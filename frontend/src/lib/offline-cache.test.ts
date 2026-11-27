import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient } from '@tanstack/react-query';
import { CACHE_KEY, restoreCache } from './offline-cache';

const store = new Map<string, string>();

beforeEach(() => {
  store.clear();
  vi.stubGlobal('localStorage', {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => store.set(key, value),
    removeItem: (key: string) => store.delete(key),
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('restoreCache', () => {
  it('shows the last known account at once, but loads it again on first use', () => {
    // Saved a moment ago: younger than any staleTime
    const me = { id: 7, username: 'kim', email: null };
    store.set(CACHE_KEY, JSON.stringify({ v: 1, queries: [{ key: ['me'], data: me, updatedAt: Date.now() }] }));
    const client = new QueryClient();
    restoreCache(client);
    expect(client.getQueryData(['me'])).toEqual(me);
    expect(client.getQueryState(['me'])?.isInvalidated).toBe(true);
  });

  it('ignores what it does not keep and other versions', () => {
    const queries = [{ key: ['group', 1, '/balance'], data: { total: 5 }, updatedAt: Date.now() }];
    store.set(CACHE_KEY, JSON.stringify({ v: 1, queries }));
    const client = new QueryClient();
    restoreCache(client);
    expect(client.getQueryData(['group', 1, '/balance'])).toBeUndefined();
    store.set(CACHE_KEY, JSON.stringify({ v: 2, queries: [{ key: ['me'], data: {}, updatedAt: 0 }] }));
    restoreCache(client);
    expect(client.getQueryData(['me'])).toBeUndefined();
  });
});
