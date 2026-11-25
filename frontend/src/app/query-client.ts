import { QueryClient } from '@tanstack/react-query';

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      // Fetch the current state when returning to the app (another device may have changed it)
      refetchOnWindowFocus: true,
      // Kept in memory for a day, so the offline cache (lib/offline-cache.ts) still has the
      // group someone used this morning when they are back at the car in the evening
      gcTime: 24 * 60 * 60 * 1000,
    },
  },
});
