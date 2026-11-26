import { useEffect, useRef, useState, useSyncExternalStore, type ChangeEvent } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { ApiError, errorText, isNetworkError } from '../lib/api';
import { newDraftId } from '../lib/outbox';
import {
  canKeepPhotos,
  discardPhoto,
  photosVersion,
  queuedPhotos,
  queuePhotos,
  subscribePhotos,
  syncPhotos,
  type QueuedPhoto,
} from '../lib/photo-outbox';
import { MAX_RECEIPTS_PER_ENTRY, deleteReceipt, receiptUrl, shrinkImage, uploadReceipt, type ReceiptKind } from '../lib/receipts';
import type { Receipt } from '../lib/types';
import type { PendingPhoto } from '../hooks/useDrafts';
import { useOnline } from '../hooks/useDrafts';
import { groupKey, useGroupId } from '../hooks/useGroupData';
import { useMeta } from '../hooks/useMeta';
import { useSession } from '../hooks/useSession';
import { useT } from '../i18n';
import { ReceiptIcon } from './Icons';
import { useFeedback } from './feedback-context';

interface Props {
  kind: ReceiptKind;
  /** The saved entry (not a draft of it): photos are attached straight away */
  entryId: number | null;
  receipts: Receipt[];
  /** The draft the form was opened from: its waiting photos are shown */
  draftId?: string;
  /** Photos of an entry not saved yet; sent with it */
  pending: PendingPhoto[];
  onPendingChange: (next: PendingPhoto[]) => void;
  /** Saved photos can be deleted (not once the entry is settled) */
  canDelete: boolean;
}

interface Thumb {
  id: string;
  src: string;
  label: string;
  waiting: boolean;
  remove?: () => void;
}

/** Waiting photos of this entry or draft on this device, with object URLs for their previews. */
function useQueued(kind: ReceiptKind, entryId: number | null, draftId?: string): { photo: QueuedPhoto; url: string }[] {
  const version = useSyncExternalStore(subscribePhotos, photosVersion, photosVersion);
  const [items, setItems] = useState<{ photo: QueuedPhoto; url: string }[]>([]);
  useEffect(() => {
    let active = true;
    let urls: string[] = [];
    void queuedPhotos().then((all) => {
      if (!active) return;
      const mine = all.filter(
        (p) => (draftId !== undefined && p.draftId === draftId) || (entryId !== null && p.kind === kind && p.entryId === entryId),
      );
      const next = mine.map((photo) => ({ photo, url: URL.createObjectURL(photo.blob) }));
      urls = next.map((item) => item.url);
      setItems(next);
    });
    return () => {
      active = false;
      urls.forEach((url) => URL.revokeObjectURL(url));
    };
  }, [version, kind, entryId, draftId]);
  return items;
}

/** Photos of a fuel entry or expense: take or pick, see large, delete. */
export function ReceiptSection({ kind, entryId, receipts, draftId, pending, onPendingChange, canDelete }: Props) {
  const t = useT();
  const r = t.receipts;
  const gid = useGroupId();
  const me = useSession();
  const meta = useMeta();
  const online = useOnline();
  const queryClient = useQueryClient();
  const { confirm, toast } = useFeedback();
  const camera = useRef<HTMLInputElement>(null);
  const library = useRef<HTMLInputElement>(null);
  const viewer = useRef<HTMLDialogElement>(null);
  const [viewing, setViewing] = useState<Thumb | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState('');
  const queued = useQueued(kind, entryId, draftId);

  useEffect(() => {
    if (viewing && viewer.current && !viewer.current.open) viewer.current.showModal();
  }, [viewing]);

  // Off on this instance; unknown (offline before /meta was loaded) shows the section
  if (meta.data && meta.data.receipts !== true) return null;

  const total = receipts.length + queued.length + pending.length;
  const room = MAX_RECEIPTS_PER_ENTRY - total;
  const offlineWithoutStore = !online && !canKeepPhotos();
  const refresh = () => queryClient.invalidateQueries({ queryKey: groupKey(gid) });

  const thumbs: Thumb[] = [
    ...receipts.map((receipt, index) => ({
      id: `r${receipt.id}`,
      src: receiptUrl(gid, receipt.id),
      label: r.photo(index + 1),
      waiting: false,
      remove: canDelete
        ? async () => {
            if (!(await confirm(r.confirmDelete, { confirmLabel: t.common.delete, danger: true }))) return;
            try {
              await deleteReceipt(gid, receipt.id);
              await refresh();
              toast(r.deleted);
            } catch (failure) {
              setError(errorText(failure));
            }
          }
        : undefined,
    })),
    ...queued.map(({ photo, url }, index) => ({
      id: `q${photo.key}`,
      src: url,
      label: r.photo(receipts.length + index + 1),
      waiting: true,
      remove: () => void discardPhoto(photo.key),
    })),
    ...pending.map((photo, index) => ({
      id: `p${photo.key}`,
      src: photo.url,
      label: r.photo(receipts.length + queued.length + index + 1),
      waiting: false,
      remove: () => {
        URL.revokeObjectURL(photo.url);
        onPendingChange(pending.filter((p) => p.key !== photo.key));
      },
    })),
  ];

  /** A saved entry: send each photo now; without a connection it waits on this device. */
  const attach = async (photos: PendingPhoto[]) => {
    if (entryId === null) return;
    const items = photos.map((p) => ({ key: p.key, userId: me.id, groupId: gid, kind, entryId, draftId: null, blob: p.blob }));
    if (await queuePhotos(items)) {
      photos.forEach((p) => URL.revokeObjectURL(p.url));
      const { failed } = await syncPhotos(me.id);
      if (failed.length > 0) setError(errorText(failed[0].error));
      else if (!online) toast(r.waiting);
    } else {
      for (const photo of photos) {
        try {
          await uploadReceipt(gid, kind, entryId, photo.blob, photo.key);
        } catch (failure) {
          setError(failure instanceof ApiError && !isNetworkError(failure) ? errorText(failure) : r.notKept);
          break;
        } finally {
          URL.revokeObjectURL(photo.url);
        }
      }
    }
    await refresh();
  };

  const pick = async (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    event.target.value = '';
    if (files.length === 0) return;
    setError('');
    const chosen = files.slice(0, Math.max(0, room));
    const photos: PendingPhoto[] = [];
    try {
      for (const [index, file] of chosen.entries()) {
        setBusy(r.preparing(index + 1, chosen.length));
        const blob = await shrinkImage(file);
        photos.push({ key: newDraftId(), blob, url: URL.createObjectURL(blob) });
      }
    } catch {
      setError(r.unreadable);
    }
    if (files.length > chosen.length) setError(r.tooMany(MAX_RECEIPTS_PER_ENTRY));
    try {
      if (photos.length === 0) return;
      if (entryId !== null && !draftId) {
        setBusy(r.sending);
        await attach(photos);
      } else {
        onPendingChange([...pending, ...photos]);
      }
    } finally {
      setBusy(null);
    }
  };

  const closeViewer = () => {
    viewer.current?.close();
    setViewing(null);
  };

  return (
    <section className="receipts" aria-labelledby="receipts-title">
      <h2 className="receipts-title" id="receipts-title">
        {r.title} <span className="hint">{t.common.optional}</span>
      </h2>
      {thumbs.length > 0 && (
        <ul className="receipt-grid">
          {thumbs.map((thumb) => (
            <li key={thumb.id}>
              <button type="button" className="receipt-thumb" onClick={() => setViewing(thumb)} aria-label={r.show(thumb.label)}>
                <img src={thumb.src} alt="" loading="lazy" />
              </button>
              {thumb.waiting && <span className="badge warn">{t.offline.stateWaiting}</span>}
              {thumb.remove && (
                <button type="button" className="link-button small" onClick={thumb.remove} aria-label={r.remove(thumb.label)}>
                  {t.common.remove}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {offlineWithoutStore && entryId === null && <p className="hint">{r.offlineUnavailable}</p>}
      {room > 0 ? (
        <div className="button-row">
          <button type="button" className="button" onClick={() => camera.current?.click()} disabled={busy !== null}>
            <ReceiptIcon /> {r.take}
          </button>
          <button type="button" className="button" onClick={() => library.current?.click()} disabled={busy !== null}>
            {r.choose}
          </button>
          <input ref={camera} type="file" accept="image/*" capture="environment" hidden onChange={pick} data-testid="receipt-camera" />
          <input ref={library} type="file" accept="image/*" multiple hidden onChange={pick} data-testid="receipt-library" />
        </div>
      ) : (
        <p className="hint">{r.full(MAX_RECEIPTS_PER_ENTRY)}</p>
      )}
      {busy && <p className="hint" role="status">{busy}</p>}
      {error && <p className="error small" role="alert">{error}</p>}
      <dialog ref={viewer} className="dialog receipt-viewer" aria-label={viewing?.label} onClose={() => setViewing(null)}>
        {viewing && (
          <>
            <img src={viewing.src} alt={viewing.label} />
            <div className="button-row">
              <a className="button" href={viewing.src} target="_blank" rel="noopener">{r.open}</a>
              <button type="button" className="button primary" onClick={closeViewer} autoFocus>{r.close}</button>
            </div>
          </>
        )}
      </dialog>
    </section>
  );
}
