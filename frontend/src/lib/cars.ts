import type { Car, Trip } from './types';

/** What the fuel button says: "fuel", "charge" or both, depending on the group's active cars. */
export function energyKind(cars: Car[]): 'fuel' | 'charge' | 'both' {
  const active = cars.filter((c) => !c.archived);
  const electric = active.filter((c) => c.energy_unit === 'kWh').length;
  if (electric === 0) return 'fuel';
  return electric === active.length ? 'charge' : 'both';
}

/**
 * Car to preselect in a new entry: the only active car, otherwise the car of the
 * person's most recent trip (trips arrive newest first), otherwise none.
 */
export function defaultCarId(cars: Car[], trips: Trip[] | undefined, userId: number): number | null {
  const active = cars.filter((c) => !c.archived);
  if (active.length === 1) return active[0].id;
  const recent = trips?.find((t) => t.shares.some((s) => s.user_id === userId) && active.some((c) => c.id === t.car_id));
  return recent?.car_id ?? null;
}
