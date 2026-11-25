import { describe, expect, it } from 'vitest';
import { describeError, describeWarning, isErrorDetail } from './errors';
import { createFormat } from './format';

// Outside React the active language follows the browser; in Node there is none, so English applies.
const de = createFormat('de');

describe('describeError', () => {
  it('translates known codes and formats their parameters', () => {
    const detail = {
      code: 'trip_overlap',
      params: { start_km: 10000, end_km: 10100, date: '2026-11-10' },
      message: 'Overlaps the trip km 10000-10100 on 2026-11-10',
    };
    expect(describeError(detail, de)).toBe('Overlaps the trip 10.000 km – 10.100 km on 10.11.2026.');
  });

  it('falls back to the server message for unknown codes', () => {
    expect(describeError({ code: 'something_new', params: {}, message: 'Something new' })).toBe('Something new');
  });

  it('recognises coded details only', () => {
    expect(isErrorDetail({ code: 'x', params: {}, message: '' })).toBe(true);
    expect(isErrorDetail('text')).toBe(false);
    expect(isErrorDetail([{ loc: ['body'] }])).toBe(false);
  });
});

describe('describeWarning', () => {
  it('translates warnings with parameters', () => {
    expect(
      describeWarning(
        { code: 'km_gap', message: '…', params: { car: 'Test car', from_km: 100, to_km: 150 } },
        de,
      ),
    ).toBe('Test car: 100 km – 150 km is not assigned to a trip');
  });

  it('shows stored messages of old settlements unchanged', () => {
    const old = { code: 'km_gap', message: 'Golf: km 100–150 ist keiner Fahrt zugeordnet' };
    expect(describeWarning(old)).toBe(old.message);
    // the API fills in an empty params object for old snapshots
    expect(describeWarning({ ...old, params: {} })).toBe(old.message);
  });
});
