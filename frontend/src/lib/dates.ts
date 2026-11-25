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
