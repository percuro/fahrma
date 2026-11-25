import { describe, expect, it } from 'vitest';
import { addDays, addMinutes, coversDay, nextQuarter, nowIn, weekStart } from './dates';

describe('calendar days', () => {
  it('adds days across months, years and clock changes', () => {
    expect(addDays('2026-11-30', 1)).toBe('2026-12-01');
    expect(addDays('2026-12-31', 1)).toBe('2027-01-01');
    expect(addDays('2027-03-28', -1)).toBe('2027-03-27');
    expect(addDays('2027-03-27', 7)).toBe('2027-04-03');
  });

  it('starts weeks on Monday', () => {
    expect(weekStart('2026-12-02')).toBe('2026-11-30'); // Wednesday
    expect(weekStart('2026-11-30')).toBe('2026-11-30'); // Monday
    expect(weekStart('2026-12-06')).toBe('2026-11-30'); // Sunday
  });
});

describe('wall-clock times', () => {
  it('reads the time in a time zone', () => {
    const moment = new Date('2026-12-01T07:07:30Z');
    expect(nowIn('Europe/Vienna', moment)).toBe('2026-12-01T08:07');
    expect(nowIn('UTC', moment)).toBe('2026-12-01T07:07');
    expect(nowIn('America/New_York', new Date('2026-12-01T03:00:00Z'))).toBe('2026-11-30T22:00');
  });

  it('rounds up to quarters and adds minutes', () => {
    expect(nextQuarter('2026-12-01T08:07')).toBe('2026-12-01T08:15');
    expect(nextQuarter('2026-12-01T08:15')).toBe('2026-12-01T08:15');
    expect(nextQuarter('2026-12-31T23:50')).toBe('2027-01-01T00:00');
    expect(addMinutes('2026-12-01T23:00', 120)).toBe('2026-12-02T01:00');
  });

  it('knows which days a period touches', () => {
    expect(coversDay('2026-12-01T22:00', '2026-12-02T02:00', '2026-12-01')).toBe(true);
    expect(coversDay('2026-12-01T22:00', '2026-12-02T02:00', '2026-12-02')).toBe(true);
    expect(coversDay('2026-12-01T22:00', '2026-12-02T00:00', '2026-12-02')).toBe(false);
    expect(coversDay('2026-12-01T22:00:00', '2026-12-02T00:00:00', '2026-12-02')).toBe(false);
    expect(coversDay('2026-12-01T22:00', '2026-12-02T02:00', '2026-11-30')).toBe(false);
  });
});
