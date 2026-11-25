import { useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { syncDrafts } from '../lib/outbox';
import { groupKey } from '../hooks/useGroupData';
import { useDrafts, useOnline } from '../hooks/useDrafts';
import { useSession } from '../hooks/useSession';
import { useT } from '../i18n';
import { useFeedback } from './feedback-context';

const RETRY_MS = 30_000;

/** Sends waiting drafts when the app starts, comes back online or into view, and every 30 s. */
export function OfflineSync() {
  const me = useSession();
  const t = useT();
  const { toast } = useFeedback();
  const queryClient = useQueryClient();
  const drafts = useDrafts();
  const online = useOnline();
  const waiting = drafts.some((d) => !d.error);

  useEffect(() => {
    if (!waiting || !online) return;
    const run = async () => {
      const { sent, failed } = await syncDrafts(me.id);
      for (const gid of new Set(sent.map((d) => d.groupId))) {
        void queryClient.invalidateQueries({ queryKey: groupKey(gid) });
      }
      if (sent.length > 0) toast(t.offline.sent(sent.length));
      if (failed.length > 0) toast(t.offline.failed(failed.length));
    };
    const onVisible = () => {
      if (document.visibilityState === 'visible') void run();
    };
    void run();
    const timer = setInterval(() => void run(), RETRY_MS);
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      clearInterval(timer);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [waiting, online, me.id, queryClient, toast, t]);

  return null;
}

/** Shown while the device reports no network. */
export function OfflineBanner() {
  const t = useT();
  const online = useOnline();
  if (online) return null;
  return <div className="offline-banner" role="status">{t.offline.banner}</div>;
}
