import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  allDrafts,
  draftLastKm,
  putDraft,
  removeUserDrafts,
  resetDraftsForTests,
  sendEntry,
  syncDrafts,
  type Draft,
} from './outbox';
import { isKept } from './offline-cache';
import type { TripWrite } from './types';

const trip = (start: number, end: number | null, car = 1): TripWrite => ({
  car_id: car, date: '2026-11-25', start_km: start, end_km: end, note: null, shares: [{ user_id: 7, weight: 1 }], external: [],
});

function respond(status: number, body: unknown = {}, headers: Record<string, string> = {}) {
  return new Response(status === 204 ? null : JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json', ...headers } });
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  resetDraftsForTests();
  removeUserDrafts(7);
  removeUserDrafts(8);
  fetchMock = vi.fn();
  vi.stubGlobal('fetch', fetchMock);
  vi.stubGlobal('window', { dispatchEvent: () => true });
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.stubGlobal('navigator', { language: '', languages: [] });
});

describe('drafts', () => {
  it('keeps its place in the queue when changed, and loses its error', async () => {
    putDraft({ id: 'aaaaaaaa', userId: 7, groupId: 1, kind: 'trip', entityId: null, body: trip(100, 150) });
    const created = allDrafts()[0].createdAt;
    putDraft({ id: 'aaaaaaaa', userId: 7, groupId: 1, kind: 'trip', entityId: null, body: trip(100, 160) });
    expect(allDrafts()).toHaveLength(1);
    expect(allDrafts()[0].createdAt).toBe(created);
    expect((allDrafts()[0] as Draft<'trip'>).body.end_km).toBe(160);
  });

  it('sends oldest first with the draft id as Idempotency-Key and stops at a connection problem', async () => {
    putDraft({ id: 'first-001', userId: 7, groupId: 1, kind: 'trip', entityId: null, body: trip(100, 150) });
    await new Promise((r) => setTimeout(r, 2));
    putDraft({ id: 'second-02', userId: 7, groupId: 1, kind: 'fuel', entityId: null, body: { car_id: 1, date: '2026-11-25', odometer_km: null, quantity_milli: null, amount_cents: 5000, paid_by_user_id: 7, full_tank: true, note: null } });
    putDraft({ id: 'other-001', userId: 8, groupId: 1, kind: 'trip', entityId: null, body: trip(200, 250) });
    fetchMock.mockResolvedValueOnce(respond(201, { id: 1 })).mockRejectedValueOnce(new TypeError('Failed to fetch'));

    const result = await syncDrafts(7);

    expect(result.sent.map((d) => d.id)).toEqual(['first-001']);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/api/v1/groups/1/trips');
    expect(new Headers(init.headers).get('Idempotency-Key')).toBe('first-001');
    // The fuel draft waits for the next attempt, the other person's draft is not touched
    expect(allDrafts().map((d) => d.id).sort()).toEqual(['other-001', 'second-02']);
    expect(allDrafts().every((d) => !d.error)).toBe(true);
  });

  it('marks a refused draft and goes on with the next', async () => {
    putDraft({ id: 'refused-1', userId: 7, groupId: 1, kind: 'trip', entityId: null, body: trip(100, 150) });
    await new Promise((r) => setTimeout(r, 2));
    putDraft({ id: 'accepted1', userId: 7, groupId: 1, kind: 'finish', entityId: 3, body: { end_km: 300 } });
    fetchMock
      .mockResolvedValueOnce(respond(409, { detail: { code: 'trip_overlap', params: {}, message: 'x' } }))
      .mockResolvedValueOnce(respond(200, { id: 3 }));

    const result = await syncDrafts(7);

    expect(result.failed.map((d) => d.id)).toEqual(['refused-1']);
    expect(result.sent.map((d) => d.id)).toEqual(['accepted1']);
    expect(fetchMock.mock.calls[1][0]).toBe('/api/v1/groups/1/trips/3/finish');
    expect(allDrafts()).toHaveLength(1);
    expect(allDrafts()[0].error).toEqual({ status: 409, detail: { code: 'trip_overlap', params: {}, message: 'x' } });
    // Refused drafts are not sent again by themselves
    fetchMock.mockClear();
    await syncDrafts(7);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('writes the current content over an entry that an earlier attempt saved', async () => {
    fetchMock
      .mockResolvedValueOnce(respond(200, { id: 42 }, { 'Idempotent-Replayed': 'true' }))
      .mockResolvedValueOnce(respond(200, { id: 42, end_km: 160 }));
    const result = await sendEntry(1, 'trip', null, trip(100, 160), 'edited-01');
    expect(fetchMock.mock.calls[1][0]).toBe('/api/v1/groups/1/trips/42');
    expect((fetchMock.mock.calls[1][1] as RequestInit).method).toBe('PUT');
    expect(result).toEqual({ id: 42, end_km: 160 });
  });

  it('changes to existing entries go as PUT without a key', async () => {
    fetchMock.mockResolvedValueOnce(respond(200, { id: 5 }));
    await sendEntry(1, 'expense', 5, { car_id: null, trip_id: null, date: '2026-11-25', category: 'other', description: null, amount_cents: 100, paid_by_user_id: 7, allocation: 'equal', allocated_user_id: null }, 'unused-01');
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect([url, init.method]).toEqual(['/api/v1/groups/1/expenses/5', 'PUT']);
    expect(new Headers(init.headers).has('Idempotency-Key')).toBe(false);
  });
});

describe('draftLastKm', () => {
  it('knows the odometer from drafted and finished trips of a car', () => {
    const drafts = [
      { kind: 'trip', body: trip(100, 150) },
      { kind: 'trip', body: trip(150, null) },
      { kind: 'trip', body: trip(900, 950, 2) },
      { kind: 'finish', entityId: 3, body: { end_km: 400 } },
    ] as Draft[];
    expect(draftLastKm(drafts, 1)).toBe(150);
    expect(draftLastKm(drafts, 1, [{ id: 3, car_id: 1 }])).toBe(400);
    expect(draftLastKm(drafts, 2)).toBe(950);
    expect(draftLastKm([], 1)).toBe(0);
  });
});

describe('offline cache', () => {
  it('keeps account, group, cars and trips – never balances', () => {
    expect(isKept(['me'])).toBe(true);
    expect(isKept(['group', 1, ''])).toBe(true);
    expect(isKept(['group', 1, '/cars'])).toBe(true);
    expect(isKept(['group', 1, '/trips'])).toBe(true);
    expect(isKept(['group', 1, '/balance'])).toBe(false);
    expect(isKept(['group', 1, '/trips/5'])).toBe(false);
    expect(isKept(['group', 1, '/settlements'])).toBe(false);
    expect(isKept(['meta'])).toBe(false);
  });
});
