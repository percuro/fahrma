import { isNetworkError } from '../lib/api';
import { LoadError, Loading } from './Status';

interface QueryLike {
  isError: boolean;
  error: unknown;
  data?: unknown;
  refetch: () => unknown;
}

/** A query that failed for lack of a connection but still has the last known data (offline cache). */
export const usableOffline = (q: QueryLike) => q.data !== undefined && isNetworkError(q.error);

/** Error or loading state for one or more queries; null when all have data. */
export function queryState(queries: QueryLike[], ready: boolean) {
  const failed = queries.find((q) => q.isError && !usableOffline(q));
  if (failed) return <LoadError error={failed.error} onRetry={() => queries.forEach((q) => void q.refetch())} />;
  if (!ready) return <Loading />;
  return null;
}
