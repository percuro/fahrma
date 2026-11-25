import { useEffect, useMemo, useState, useSyncExternalStore } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { isNetworkError } from '../lib/api';
import {
  allDrafts,
  newDraftId,
  putDraft,
  removeDraft,
  sendEntry,
  subscribeDrafts,
  type Draft,
  type DraftBodies,
  type DraftKind,
} from '../lib/outbox';
import { groupKey, useGroupId } from './useGroupData';
import { useSession } from './useSession';

/** The signed-in person's drafts, optionally of one group (oldest first). */
export function useDrafts(groupId?: number): Draft[] {
  const me = useSession();
  const list = useSyncExternalStore(subscribeDrafts, allDrafts, allDrafts);
  return useMemo(
    () =>
      list
        .filter((d) => d.userId === me.id && (groupId === undefined || d.groupId === groupId))
        .sort((a, b) => a.createdAt.localeCompare(b.createdAt)),
    [list, me.id, groupId],
  );
}

/** navigator.onLine: false means certainly offline; true only means "maybe". */
export function useOnline(): boolean {
  const [online, setOnline] = useState(() => typeof navigator === 'undefined' || navigator.onLine !== false);
  useEffect(() => {
    const update = () => setOnline(navigator.onLine !== false);
    window.addEventListener('online', update);
    window.addEventListener('offline', update);
    return () => {
      window.removeEventListener('online', update);
      window.removeEventListener('offline', update);
    };
  }, []);
  return online;
}

export type SaveOutcome = 'sent' | 'draft';

/**
 * Save an entry: straight to the server, or – without a connection – as a draft on this device
 * that is sent later. The key stays the same for the life of the form (or is the draft's id),
 * so an attempt that did arrive is never saved twice.
 */
export function useEntrySave<K extends DraftKind>(kind: K, entityId: number | null, draft?: Draft) {
  const gid = useGroupId();
  const me = useSession();
  const queryClient = useQueryClient();
  const [key] = useState(() => draft?.id ?? newDraftId());
  return useMutation({
    // Runs offline too (TanStack would pause it): that is exactly when it keeps a draft
    networkMode: 'always',
    mutationFn: async (body: DraftBodies[K]): Promise<SaveOutcome> => {
      const keep = () => putDraft<K>({ id: key, userId: me.id, groupId: gid, kind, entityId, body });
      if (typeof navigator !== 'undefined' && navigator.onLine === false) {
        keep();
        return 'draft';
      }
      try {
        await sendEntry(gid, kind, entityId, body, key);
      } catch (error) {
        if (!isNetworkError(error)) throw error;
        keep();
        return 'draft';
      }
      if (draft) removeDraft(draft.id);
      await queryClient.invalidateQueries({ queryKey: groupKey(gid) });
      return 'sent';
    },
  });
}
