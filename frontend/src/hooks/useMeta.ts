import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../lib/api';
import type { Meta } from '../lib/types';

export const META_KEY = ['meta'] as const;

/** Public facts about the instance: setup, registration mode, operator links, limits. */
export function useMeta() {
  return useQuery({
    queryKey: META_KEY,
    queryFn: () => apiFetch<Meta>('/v1/meta'),
    retry: false,
    staleTime: 5 * 60_000,
  });
}
