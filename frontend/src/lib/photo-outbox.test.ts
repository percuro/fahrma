import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  canKeepPhotos,
  discardDraftPhotos,
  discardUserPhotos,
  memoryPhotoStore,
  queuedPhotos,
  queuePhotos,
  setPhotoStoreForTests,
  syncPhotos,
} from './photo-outbox';
import { putDraft, removeUserDrafts, resetDraftsForTests, syncDrafts } from './outbox';
import { fitWithin } from './receipts';
import type { FuelWrite } from './types';

const fuel: FuelWrite = {
  car_id: 1, date: '2026-11-25', odometer_km: null, quantity_milli: null, amount_cents: 5000, paid_by_user_id: 7, full_tank: true, note: null,
};
const blob = () => new Blob([new Uint8Array([0xff, 0xd8, 0xff, 0xd9])], { type: 'image/jpeg' });
const photo = (key: string, entryId: number | null, draftId: string | null, userId = 7) => ({
  key, userId, groupId: 1, kind: 'fuel' as const, entryId, draftId, blob: blob(),
});

function respond(status: number, body: unknown = {}, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json', ...headers } });
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  setPhotoStoreForTests(memoryPhotoStore());
  resetDraftsForTests();
  removeUserDrafts(7);
  fetchMock = vi.fn();
  vi.stubGlobal('fetch', fetchMock);
  vi.stubGlobal('window', { dispatchEvent: () => true });
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.stubGlobal('navigator', { language: '', languages: [] });
  setPhotoStoreForTests(null);
});

describe('shrinking', () => {
  it('fits the longer side and keeps the proportions', () => {
    expect(fitWithin(4032, 3024)).toEqual({ width: 1600, height: 1200 });
    expect(fitWithin(3024, 4032)).toEqual({ width: 1200, height: 1600 });
  });

  it('never makes a photo larger', () => {
    expect(fitWithin(800, 600)).toEqual({ width: 800, height: 600 });
  });
});

describe('waiting photos', () => {
  it('sends a photo of a saved entry with its key as Idempotency-Key', async () => {
    await queuePhotos([photo('photo-key-1', 12, null)]);
    fetchMock.mockResolvedValueOnce(respond(201, { id: 5 }));

    const result = await syncPhotos(7);

    expect(result.sent.map((p) => p.key)).toEqual(['photo-key-1']);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/api/v1/groups/1/fuel/12/receipts');
    const headers = new Headers(init.headers);
    expect(headers.get('Idempotency-Key')).toBe('photo-key-1');
    expect(headers.get('Content-Type')).toBe('image/jpeg');
    expect(init.body).toBeInstanceOf(Blob);
    expect(await queuedPhotos()).toEqual([]);
  });

  it('keeps the photo when there is no connection, drops it when the server refuses', async () => {
    await queuePhotos([photo('photo-key-1', 12, null)]);
    fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'));
    expect((await syncPhotos(7)).sent).toEqual([]);
    expect(await queuedPhotos()).toHaveLength(1);

    fetchMock.mockResolvedValueOnce(respond(409, { detail: { code: 'limit_reached', params: { limit: 'receipt_mb_per_group', max: 1 }, message: 'x' } }));
    const result = await syncPhotos(7);
    expect(result.failed.map((f) => f.error.code)).toEqual(['limit_reached']);
    expect(await queuedPhotos()).toEqual([]);
  });

  it('waits for its draft and goes once the draft is saved', async () => {
    putDraft({ id: 'draft-0001', userId: 7, groupId: 1, kind: 'fuel', entityId: null, body: fuel });
    await queuePhotos([photo('photo-key-1', null, 'draft-0001'), photo('photo-key-2', null, 'draft-0001')]);

    expect((await syncPhotos(7)).sent).toEqual([]);
    expect(fetchMock).not.toHaveBeenCalled();

    fetchMock.mockResolvedValueOnce(respond(201, { id: 42 }));
    await syncDrafts(7);
    const waiting = await queuedPhotos();
    expect(waiting.map((p) => [p.entryId, p.draftId])).toEqual([[42, null], [42, null]]);

    fetchMock.mockImplementation(async () => respond(201, { id: 1 }));
    await syncPhotos(7);
    expect(fetchMock.mock.calls.slice(1).map((call) => call[0])).toEqual([
      '/api/v1/groups/1/fuel/42/receipts',
      '/api/v1/groups/1/fuel/42/receipts',
    ]);
    expect(await queuedPhotos()).toEqual([]);
  });

  it('goes with a discarded draft, and with the person on logout', async () => {
    await queuePhotos([photo('photo-key-1', null, 'draft-0001'), photo('photo-key-2', 3, null), photo('photo-key-3', 3, null, 8)]);
    await discardDraftPhotos('draft-0001');
    expect((await queuedPhotos()).map((p) => p.key).sort()).toEqual(['photo-key-2', 'photo-key-3']);
    await discardUserPhotos(7);
    expect((await queuedPhotos()).map((p) => p.key)).toEqual(['photo-key-3']);
  });

  it('drops photos of a draft that no longer exists', async () => {
    await queuePhotos([photo('photo-key-1', null, 'gone-draft')]);
    await syncPhotos(7);
    expect(await queuedPhotos()).toEqual([]);
  });

  it('reports when the device cannot keep photos', async () => {
    setPhotoStoreForTests(null);
    expect(canKeepPhotos()).toBe(false);
    expect(await queuePhotos([photo('photo-key-1', 12, null)])).toBe(false);
  });
});

describe('order', () => {
  it('sends photos picked together in the order they were picked', async () => {
    await queuePhotos([photo('zzzz-first', 12, null), photo('aaaa-second', 12, null)]);
    fetchMock.mockImplementation(async () => respond(201, { id: 1 }));
    const result = await syncPhotos(7);
    expect(result.sent.map((p) => p.key)).toEqual(['zzzz-first', 'aaaa-second']);
  });
});
