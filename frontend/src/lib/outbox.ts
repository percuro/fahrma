/**
 * Drafts: entries saved on this device while the server cannot be reached (underground car
 * park, dead spot). They are sent in the order they were made as soon as there is a connection.
 *
 * Every draft carries a random id that is sent as Idempotency-Key: if a request reached the
 * server but its answer got lost, sending the draft again returns the saved entry instead of a
 * second copy.
 */
import { ApiError, apiRequest, isNetworkError } from './api';
import type { ExpenseWrite, FuelWrite, TripWrite } from './types';

export type DraftKind = 'trip' | 'fuel' | 'expense' | 'finish';

export interface DraftBodies {
  trip: TripWrite;
  fuel: FuelWrite;
  expense: ExpenseWrite;
  finish: { end_km: number };
}

export interface Draft<K extends DraftKind = DraftKind> {
  id: string;
  userId: number;
  groupId: number;
  kind: K;
  /** The entry being changed or the trip being finished; null for a new entry */
  entityId: number | null;
  body: DraftBodies[K];
  createdAt: string;
  /** The server refused it (not a connection problem): shown until changed or discarded */
  error?: { status: number; detail: unknown };
}

export const DRAFTS_KEY = 'fahrma:drafts';
const SEND_TIMEOUT_MS = 20_000;

const COLLECTION: Record<Exclude<DraftKind, 'finish'>, string> = { trip: 'trips', fuel: 'fuel', expense: 'expenses' };

let drafts: Draft[] | null = null;
const listeners = new Set<() => void>();

function storage(): Storage | null {
  try {
    return globalThis.localStorage ?? null;
  } catch {
    return null;
  }
}

function load(): Draft[] {
  if (drafts === null) {
    try {
      const parsed = JSON.parse(storage()?.getItem(DRAFTS_KEY) ?? '[]') as unknown;
      drafts = Array.isArray(parsed) ? (parsed as Draft[]) : [];
    } catch {
      drafts = [];
    }
  }
  return drafts;
}

function store(next: Draft[]): void {
  drafts = next;
  try {
    storage()?.setItem(DRAFTS_KEY, JSON.stringify(next));
  } catch {
    // Storage full or blocked: the drafts live until the page is closed
  }
  listeners.forEach((listener) => listener());
}

/** For useSyncExternalStore: the same array until something changes. */
export function allDrafts(): Draft[] {
  return load();
}

export function subscribeDrafts(listener: () => void): () => void {
  listeners.add(listener);
  // Another tab changed the drafts
  const onStorage = (event: StorageEvent) => {
    if (event.key !== DRAFTS_KEY) return;
    drafts = null;
    listener();
  };
  globalThis.addEventListener?.('storage', onStorage);
  return () => {
    listeners.delete(listener);
    globalThis.removeEventListener?.('storage', onStorage);
  };
}

export function findDraft(id: string | null | undefined): Draft | undefined {
  return id ? load().find((d) => d.id === id) : undefined;
}

/** Add or replace a draft; a changed draft loses its error and keeps its place in the queue. */
export function putDraft<K extends DraftKind>(draft: Omit<Draft<K>, 'createdAt' | 'error'>): void {
  const current = load();
  const existing = current.find((d) => d.id === draft.id);
  const next: Draft = { ...draft, createdAt: existing?.createdAt ?? new Date().toISOString() } as Draft;
  store(existing ? current.map((d) => (d.id === draft.id ? next : d)) : [...current, next]);
}

export function removeDraft(id: string): void {
  store(load().filter((d) => d.id !== id));
}

export function removeUserDrafts(userId: number): void {
  store(load().filter((d) => d.userId !== userId));
}

/** Clear the error so the next sync tries again. */
export function retryDraft(id: string): void {
  store(load().map((d) => (d.id === id ? { ...d, error: undefined } : d)));
}

export function newDraftId(): string {
  // randomUUID only exists on https (or localhost); a self-hosted instance may run on plain http
  const random = globalThis.crypto as Crypto & { randomUUID?: () => string };
  if (typeof random.randomUUID === 'function') return random.randomUUID();
  const bytes = new Uint8Array(16);
  random.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
}

function timeout(): AbortSignal | undefined {
  return typeof AbortSignal !== 'undefined' && 'timeout' in AbortSignal ? AbortSignal.timeout(SEND_TIMEOUT_MS) : undefined;
}

/**
 * Send an entry to the server. New entries go with the draft id as Idempotency-Key; when the
 * server already had them (an earlier attempt arrived), the current content is written over it.
 */
export async function sendEntry<K extends DraftKind>(
  groupId: number,
  kind: K,
  entityId: number | null,
  body: DraftBodies[K],
  key: string,
): Promise<unknown> {
  const base = `/v1/groups/${groupId}`;
  const json = JSON.stringify(body);
  if (kind === 'finish') {
    const { data } = await apiRequest(`${base}/trips/${entityId}/finish`, {
      method: 'POST',
      body: json,
      headers: { 'Idempotency-Key': key },
      signal: timeout(),
    });
    return data;
  }
  const collection = COLLECTION[kind as Exclude<DraftKind, 'finish'>];
  if (entityId !== null) {
    return (await apiRequest(`${base}/${collection}/${entityId}`, { method: 'PUT', body: json, signal: timeout() })).data;
  }
  const { data, response } = await apiRequest<{ id: number }>(`${base}/${collection}`, {
    method: 'POST',
    body: json,
    headers: { 'Idempotency-Key': key },
    signal: timeout(),
  });
  if (response.headers.get('Idempotent-Replayed') === 'true') {
    try {
      return (await apiRequest(`${base}/${collection}/${data.id}`, { method: 'PUT', body: json, signal: timeout() })).data;
    } catch (error) {
      // Settled in the meantime: the entry exists, it just cannot change any more
      if (error instanceof ApiError && error.code === 'already_settled') return data;
      throw error;
    }
  }
  return data;
}

export interface SyncResult {
  sent: Draft[];
  failed: Draft[];
}

let running: Promise<SyncResult> | null = null;

/** Send the person's waiting drafts, oldest first; stops at the first connection problem. */
export function syncDrafts(userId: number): Promise<SyncResult> {
  running ??= (async () => {
    const result: SyncResult = { sent: [], failed: [] };
    const waiting = load()
      .filter((d) => d.userId === userId && !d.error)
      .sort((a, b) => a.createdAt.localeCompare(b.createdAt));
    for (const draft of waiting) {
      try {
        await sendEntry(draft.groupId, draft.kind, draft.entityId, draft.body, draft.id);
        removeDraft(draft.id);
        result.sent.push(draft);
      } catch (error) {
        if (isNetworkError(error) || !(error instanceof ApiError) || error.status === 401) break;
        const failed = { ...draft, error: { status: error.status, detail: error.detail } };
        store(load().map((d) => (d.id === draft.id ? failed : d)));
        result.failed.push(failed);
      }
    }
    return result;
  })().finally(() => {
    running = null;
  });
  return running;
}

/** The highest odometer reading the person's drafts know for a car (for the next trip's start). */
export function draftLastKm(list: Draft[], carId: number | null, trips: { id: number; car_id: number }[] = []): number {
  let km = 0;
  for (const d of list) {
    if (d.kind === 'trip') {
      const body = d.body as TripWrite;
      if (body.car_id === carId) km = Math.max(km, body.end_km ?? body.start_km);
    } else if (d.kind === 'finish' && trips.some((t) => t.id === d.entityId && t.car_id === carId)) {
      km = Math.max(km, (d.body as { end_km: number }).end_km);
    }
  }
  return km;
}

/** Why the server refused a draft, as an error that errorText() can describe. */
export function draftError(draft: Draft | undefined): ApiError | null {
  if (!draft?.error) return null;
  return new ApiError(`HTTP ${draft.error.status}`, draft.error.status, draft.error.detail);
}

/** For tests */
export function resetDraftsForTests(): void {
  drafts = null;
}
