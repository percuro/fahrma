export function todayIso(): string {
  const now = new Date();
  const offset = now.getTimezoneOffset() * 60_000;
  return new Date(now.getTime() - offset).toISOString().slice(0, 10);
}

/**
 * Today in a time zone (the group's), computed on the device: the "today" the server sent may
 * be days old when the group comes from the offline cache.
 */
export function todayIn(timezone: string, fallback: string): string {
  try {
    // en-CA formats as YYYY-MM-DD
    return new Intl.DateTimeFormat('en-CA', { timeZone: timezone, year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
  } catch {
    return fallback;
  }
}

/*
 * Reservations use wall-clock times in the group's time zone as plain strings
 * ("2026-12-01T08:00"), exactly as the API sends them. Day arithmetic below works on
 * calendar dates only (via UTC), so the device's own time zone never shifts a day.
 */

const isoDay = (date: Date) => date.toISOString().slice(0, 10);
const asUtc = (day: string) => {
  const [y, m, d] = day.split('-').map(Number);
  return new Date(Date.UTC(y, m - 1, d));
};

/** "2026-12-01" plus n days. */
export function addDays(day: string, n: number): string {
  const date = asUtc(day);
  date.setUTCDate(date.getUTCDate() + n);
  return isoDay(date);
}

/** The Monday of the week a day belongs to. */
export function weekStart(day: string): string {
  const weekday = (asUtc(day).getUTCDay() + 6) % 7; // Monday = 0
  return addDays(day, -weekday);
}

/** Wall-clock time now in a time zone, to the minute: "2026-12-01T08:07". */
export function nowIn(timezone: string, now: Date = new Date()): string {
  try {
    const parts = Object.fromEntries(
      new Intl.DateTimeFormat('en-CA', {
        timeZone: timezone, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
      }).formatToParts(now).map((p) => [p.type, p.value]),
    );
    return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`;
  } catch {
    return now.toISOString().slice(0, 16);
  }
}

/** Plus minutes on a wall-clock time (calendar arithmetic, ignoring clock changes). */
export function addMinutes(local: string, minutes: number): string {
  const date = new Date(`${local.slice(0, 16)}:00Z`);
  date.setUTCMinutes(date.getUTCMinutes() + minutes);
  return date.toISOString().slice(0, 16);
}

/** The next full quarter of an hour: 08:07 → 08:15, 08:15 → 08:15. */
export function nextQuarter(local: string): string {
  const minutes = Number(local.slice(14, 16));
  const rest = minutes % 15;
  return addMinutes(local.slice(0, 16), rest === 0 ? 0 : 15 - rest);
}

/** Whether a period (local wall-clock times, end exclusive) touches a calendar day. */
export function coversDay(startsAt: string, endsAt: string, day: string): boolean {
  return startsAt.slice(0, 10) <= day && endsAt.slice(0, 16) > `${day}T00:00`;
}
