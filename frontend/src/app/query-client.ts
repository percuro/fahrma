import { QueryClient } from '@tanstack/react-query';

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      // Fetch the current state when returning to the app (another device may have changed it)
      refetchOnWindowFocus: true,
    },
  },
});
