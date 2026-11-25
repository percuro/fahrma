import { LoadError, Loading } from './Status';

interface QueryLike {
  isError: boolean;
  error: unknown;
  refetch: () => unknown;
}

/** Error or loading state for one or more queries; null when all have data. */
export function queryState(queries: QueryLike[], ready: boolean) {
  const failed = queries.find((q) => q.isError);
  if (failed) return <LoadError error={failed.error} onRetry={() => queries.forEach((q) => void q.refetch())} />;
  if (!ready) return <Loading />;
  return null;
}
