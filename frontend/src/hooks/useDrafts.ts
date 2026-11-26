import { useEffect, useMemo, useState, useSyncExternalStore } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ApiError, errorText, isNetworkError } from '../lib/api';
import { assignDraftPhotos, queuePhotos, syncPhotos } from '../lib/photo-outbox';
import { uploadReceipt, type ReceiptKind } from '../lib/receipts';
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
import { useT } from '../i18n';
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

/**
 * sent / draft: the entry went to the server or stays on this device.
 * The others only with photos: the entry was saved, and its photos wait for a connection
 * (photos-waiting), were refused by the server (photos-refused, see photoError), or could not
 * be kept on this device without a connection (photos-lost).
 */
export type SaveOutcome = 'sent' | 'draft' | 'photos-waiting' | 'photos-refused' | 'photos-lost';

/** A photo picked in a form, sent when the entry is saved. */
export interface PendingPhoto {
  /** Idempotency-Key of the photo */
  key: string;
  blob: Blob;
  /** Object URL for the preview */
  url: string;
}

/**
 * Save an entry: straight to the server, or – without a connection – as a draft on this device
 * that is sent later. The key stays the same for the life of the form (or is the draft's id),
 * so an attempt that did arrive is never saved twice. Photos of a fuel entry or expense go
 * after the entry; without a connection they wait on this device with the draft.
 */
export function useEntrySave<K extends DraftKind>(kind: K, entityId: number | null, draft?: Draft, photos: PendingPhoto[] = []) {
  const gid = useGroupId();
  const me = useSession();
  const queryClient = useQueryClient();
  const [key] = useState(() => draft?.id ?? newDraftId());
  const [photoError, setPhotoError] = useState<ApiError | null>(null);
  const mutation = useMutation({
    // Runs offline too (TanStack would pause it): that is exactly when it keeps a draft
    networkMode: 'always',
    mutationFn: async (body: DraftBodies[K]): Promise<SaveOutcome> => {
      setPhotoError(null);
      const photoKind: ReceiptKind | null = kind === 'fuel' || kind === 'expense' ? (kind as ReceiptKind) : null;
      const queue = (entryId: number | null, draftId: string | null) =>
        photoKind && photos.length > 0
          ? queuePhotos(photos.map((p) => ({ key: p.key, userId: me.id, groupId: gid, kind: photoKind, entryId, draftId, blob: p.blob })))
          : Promise.resolve(true);
      const keep = async (): Promise<SaveOutcome> => {
        putDraft<K>({ id: key, userId: me.id, groupId: gid, kind, entityId, body });
        // Photos of a changed entry can go as soon as there is a connection; those of a new one wait for its draft
        const kept = await queue(entityId, entityId === null ? key : null);
        return kept ? 'draft' : 'photos-lost';
      };
      if (typeof navigator !== 'undefined' && navigator.onLine === false) return keep();
      let saved: unknown;
      try {
        saved = await sendEntry(gid, kind, entityId, body, key);
      } catch (error) {
        if (!isNetworkError(error)) throw error;
        return keep();
      }
      const entryId = entityId ?? (saved as { id: number }).id;
      if (draft) {
        if (photoKind) await assignDraftPhotos(draft.id, entryId);
        removeDraft(draft.id);
      }
      let outcome: SaveOutcome = 'sent';
      if (photoKind && photos.length > 0) {
        if (await queue(entryId, null)) {
          const { sent, failed } = await syncPhotos(me.id);
          if (failed.length > 0) {
            setPhotoError(failed[0].error);
            outcome = 'photos-refused';
          } else if (photos.some((p) => !sent.some((s) => s.key === p.key))) {
            outcome = 'photos-waiting';
          }
        } else {
          // This device cannot keep photos: send them straight away
          for (const photo of photos) {
            try {
              await uploadReceipt(gid, photoKind, entryId, photo.blob, photo.key);
            } catch (error) {
              if (error instanceof ApiError && !isNetworkError(error)) {
                setPhotoError(error);
                outcome = 'photos-refused';
              } else {
                outcome = 'photos-lost';
              }
              break;
            }
          }
        }
      }
      await queryClient.invalidateQueries({ queryKey: groupKey(gid) });
      return outcome;
    },
  });
  return { ...mutation, photoError };
}

/** The short message after saving an entry, by how it went. */
export function useSaveMessage() {
  const t = useT();
  return (outcome: SaveOutcome, photoError: ApiError | null): string => {
    if (outcome === 'draft') return t.offline.savedAsDraft;
    if (outcome === 'sent') return t.common.saved;
    if (outcome === 'photos-refused' && photoError) return t.receipts.refused(errorText(photoError));
    return t.receipts.saved[outcome] ?? t.common.saved;
  };
}
