import { describe, expect, it } from 'vitest';
import { defaultCarId, energyKind } from './cars';
import type { Car, Trip } from './types';

const car = (id: number, energy_unit: 'l' | 'kWh' = 'l', archived = false): Car => ({
  id, name: `Car ${id}`, plate: null, start_odometer_km: 0, energy_unit, archived, last_km: 0, open_trip_id: null,
});
const trip = (car_id: number, user_id: number): Trip => ({
  id: car_id * 10 + user_id, car_id, date: '2026-11-24', start_km: 0, end_km: 1, km: 1, note: null,
  shares: [{ user_id, weight: 1 }], external: [], created_by: user_id, settlement_id: null, cost_cents: null, cost_is_estimate: true,
});

describe('energyKind', () => {
  it('names the button after the active cars', () => {
    expect(energyKind([car(1), car(2)])).toBe('fuel');
    expect(energyKind([car(1, 'kWh')])).toBe('charge');
    expect(energyKind([car(1, 'kWh'), car(2)])).toBe('both');
    expect(energyKind([car(1, 'kWh'), car(2, 'l', true)])).toBe('charge');
  });
});

describe('defaultCarId', () => {
  it('takes the only active car', () => {
    expect(defaultCarId([car(1), car(2, 'l', true)], [], 7)).toBe(1);
  });

  it('takes the car of the latest own trip, ignoring retired cars', () => {
    const cars = [car(1), car(2), car(3, 'l', true)];
    expect(defaultCarId(cars, [trip(3, 7), trip(2, 8), trip(2, 7), trip(1, 7)], 7)).toBe(2);
    expect(defaultCarId(cars, [trip(1, 8)], 7)).toBeNull();
    expect(defaultCarId(cars, undefined, 7)).toBeNull();
  });
});
