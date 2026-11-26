import { useEffect, useState, useSyncExternalStore } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { syncDrafts } from '../lib/outbox';
import { photosVersion, queuedPhotos, subscribePhotos, syncPhotos } from '../lib/photo-outbox';
import { errorText } from '../lib/api';
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
  const photos = useWaitingPhotos(me.id);
  const waiting = drafts.some((d) => !d.error) || photos;

  useEffect(() => {
    if (!waiting || !online) return;
    const run = async () => {
      const { sent, failed } = await syncDrafts(me.id);
      for (const gid of new Set(sent.map((d) => d.groupId))) {
        void queryClient.invalidateQueries({ queryKey: groupKey(gid) });
      }
      const photoResult = await syncPhotos(me.id);
      for (const gid of new Set(photoResult.sent.map((p) => p.groupId))) {
        void queryClient.invalidateQueries({ queryKey: groupKey(gid) });
      }
      if (sent.length > 0) toast(t.offline.sent(sent.length));
      if (failed.length > 0) toast(t.offline.failed(failed.length));
      if (photoResult.failed.length > 0) toast(t.receipts.refused(errorText(photoResult.failed[0].error)));
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

/** Photos of this person wait on the device (re-checked whenever the queue changes). */
function useWaitingPhotos(userId: number): boolean {
  const version = useSyncExternalStore(subscribePhotos, photosVersion, photosVersion);
  const [waiting, setWaiting] = useState(false);
  useEffect(() => {
    let active = true;
    void queuedPhotos().then((all) => {
      if (active) setWaiting(all.some((p) => p.userId === userId));
    });
    return () => {
      active = false;
    };
  }, [version, userId]);
  return waiting;
}

/** Shown while the device reports no network. */
export function OfflineBanner() {
  const t = useT();
  const online = useOnline();
  if (online) return null;
  return <div className="banner warn" role="status">{t.offline.banner}</div>;
}
