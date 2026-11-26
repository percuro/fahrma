/**
 * Receipt photos waiting on this device: taken without a connection, or attached to an entry
 * that is itself still a draft. They are kept in IndexedDB (localStorage is far too small for
 * photos) and sent after the drafts, each with its own Idempotency-Key, so a photo whose answer
 * got lost is never attached twice.
 */
import { ApiError, isNetworkError } from './api';
import { findDraft } from './outbox';
import { uploadReceipt, type ReceiptKind } from './receipts';

export interface QueuedPhoto {
  /** Sent as Idempotency-Key */
  key: string;
  userId: number;
  groupId: number;
  kind: ReceiptKind;
  /** The saved entry; null while the entry is a draft */
  entryId: number | null;
  /** The draft the photo belongs to, until that draft is sent */
  draftId: string | null;
  blob: Blob;
  createdAt: string;
}

export interface PhotoStore {
  all(): Promise<QueuedPhoto[]>;
  put(photo: QueuedPhoto): Promise<void>;
  remove(key: string): Promise<void>;
}

const DB_NAME = 'fahrma';
const STORE = 'photos';
const SEND_TIMEOUT_MS = 60_000;

function request<T>(req: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

let opening: Promise<IDBDatabase> | null = null;

function database(): Promise<IDBDatabase> {
  opening ??= new Promise<IDBDatabase>((resolve, reject) => {
    const open = indexedDB.open(DB_NAME, 1);
    open.onupgradeneeded = () => open.result.createObjectStore(STORE, { keyPath: 'key' });
    open.onsuccess = () => resolve(open.result);
    open.onerror = () => reject(open.error);
  }).catch((error: unknown) => {
    opening = null;
    throw error;
  });
  return opening;
}

async function transaction<T>(mode: IDBTransactionMode, run: (store: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  const db = await database();
  return request(run(db.transaction(STORE, mode).objectStore(STORE)));
}

/**
 * Stored as bytes, not as a Blob: Safari cannot keep Blobs in IndexedDB in a private window
 * (nor WebKit in other ephemeral sessions), while an ArrayBuffer works everywhere.
 */
type StoredPhoto = Omit<QueuedPhoto, 'blob'> & { data: ArrayBuffer; type: string };

const indexedDbStore: PhotoStore = {
  all: async () => {
    const rows = await transaction('readonly', (store) => store.getAll() as IDBRequest<StoredPhoto[]>);
    return rows.map(({ data, type, ...photo }) => ({ ...photo, blob: new Blob([data], { type }) }));
  },
  put: async ({ blob, ...photo }) => {
    // Read before the transaction starts: it would close while waiting for the bytes
    const stored: StoredPhoto = { ...photo, data: await blob.arrayBuffer(), type: blob.type || 'image/jpeg' };
    await transaction('readwrite', (store) => store.put(stored));
  },
  remove: async (key) => {
    await transaction('readwrite', (store) => store.delete(key));
  },
};

let store: PhotoStore | null = typeof indexedDB !== 'undefined' ? indexedDbStore : null;

/** Photos can be kept on this device (no IndexedDB: e.g. some private windows). */
export function canKeepPhotos(): boolean {
  return store !== null;
}

let version = 0;
const listeners = new Set<() => void>();

function changed(): void {
  version += 1;
  listeners.forEach((listener) => listener());
}

/** For useSyncExternalStore: changes whenever a photo is queued, sent or dropped. */
export function photosVersion(): number {
  return version;
}

export function subscribePhotos(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export async function queuedPhotos(): Promise<QueuedPhoto[]> {
  if (!store) return [];
  try {
    return (await store.all()).sort((a, b) => a.createdAt.localeCompare(b.createdAt));
  } catch {
    return [];
  }
}

/** Keep photos until they can be sent; false if this device cannot keep them. */
export async function queuePhotos(photos: Omit<QueuedPhoto, 'createdAt'>[]): Promise<boolean> {
  if (photos.length === 0) return true;
  if (!store) return false;
  try {
    // One millisecond apart: photos picked together are sent (and numbered) in the order picked
    const now = Date.now();
    for (const [index, photo] of photos.entries()) {
      await store.put({ ...photo, createdAt: new Date(now + index).toISOString() });
    }
    return true;
  } catch {
    return false;
  } finally {
    changed();
  }
}

/** The draft was saved as entry ``entryId``: its photos can go now. */
export async function assignDraftPhotos(draftId: string, entryId: number): Promise<void> {
  if (!store) return;
  for (const photo of await queuedPhotos()) {
    if (photo.draftId === draftId) await store.put({ ...photo, draftId: null, entryId });
  }
  changed();
}

async function removeWhere(test: (photo: QueuedPhoto) => boolean): Promise<void> {
  if (!store) return;
  try {
    for (const photo of await queuedPhotos()) if (test(photo)) await store.remove(photo.key);
  } catch {
    // Nothing kept, nothing to remove
  }
  changed();
}

/** One waiting photo taken back before it was sent. */
export function discardPhoto(key: string): Promise<void> {
  return removeWhere((photo) => photo.key === key);
}

/** The draft was discarded: so are its photos. */
export function discardDraftPhotos(draftId: string): Promise<void> {
  return removeWhere((photo) => photo.draftId === draftId);
}

/** Logged out: nothing of this person stays on the device. */
export function discardUserPhotos(userId: number): Promise<void> {
  return removeWhere((photo) => photo.userId === userId);
}

export interface PhotoSyncResult {
  sent: QueuedPhoto[];
  /** Refused by the server (e.g. no room left in the plan, entry deleted); not kept */
  failed: { photo: QueuedPhoto; error: ApiError }[];
}

function timeout(): AbortSignal | undefined {
  return typeof AbortSignal !== 'undefined' && 'timeout' in AbortSignal ? AbortSignal.timeout(SEND_TIMEOUT_MS) : undefined;
}

let running: Promise<PhotoSyncResult> | null = null;

/** Send the person's waiting photos whose entry is saved; stops at the first connection problem. */
export function syncPhotos(userId: number): Promise<PhotoSyncResult> {
  running ??= (async () => {
    const result: PhotoSyncResult = { sent: [], failed: [] };
    if (!store) return result;
    for (const photo of await queuedPhotos()) {
      if (photo.userId !== userId) continue;
      if (photo.entryId === null) {
        // Waiting for its draft; a draft that is gone (discarded elsewhere) takes its photos along
        if (photo.draftId === null || !findDraft(photo.draftId)) await store.remove(photo.key);
        continue;
      }
      try {
        await uploadReceipt(photo.groupId, photo.kind, photo.entryId, photo.blob, photo.key, timeout());
        await store.remove(photo.key);
        result.sent.push(photo);
      } catch (error) {
        if (isNetworkError(error) || !(error instanceof ApiError) || error.status === 401) break;
        await store.remove(photo.key);
        result.failed.push({ photo, error });
      }
    }
    return result;
  })().finally(() => {
    running = null;
    changed();
  });
  return running;
}

/** For tests */
export function setPhotoStoreForTests(next: PhotoStore | null): void {
  store = next;
  running = null;
}

export function memoryPhotoStore(): PhotoStore {
  const photos = new Map<string, QueuedPhoto>();
  return {
    all: async () => [...photos.values()],
    put: async (photo) => void photos.set(photo.key, photo),
    remove: async (key) => void photos.delete(key),
  };
}
