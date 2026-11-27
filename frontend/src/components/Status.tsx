import { errorText } from '../lib/api';
import { useT } from '../i18n';

export function Loading() {
  const t = useT();
  return <p className="subtle" role="status" aria-live="polite">{t.common.loading}</p>;
}

export function LoadError({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const t = useT();
  return (
    <div className="notice error-box" role="alert">
      <p className="m-0">{errorText(error) || t.common.loadFailed}</p>
      {onRetry && <button type="button" className="button small" onClick={onRetry}>{t.common.retry}</button>}
    </div>
  );
}

/** A page whose code could not be loaded (offline before it was cached, or an update in between). */
export function PageFailed() {
  const t = useT();
  return (
    <div className="notice error-box" role="alert">
      <p className="m-0">{t.common.pageFailed}</p>
      <button type="button" className="button small" onClick={() => window.location.reload()}>{t.common.retry}</button>
    </div>
  );
}
