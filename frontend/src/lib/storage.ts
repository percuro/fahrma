// Key from the working name "Autokasse"; kept so existing installations remember the last group
export const LAST_GROUP_KEY = 'autokasse:last-group';

export function readLastGroup(): number | null {
  try {
    const value = localStorage.getItem(LAST_GROUP_KEY);
    return value ? Number(value) : null;
  } catch {
    return null;
  }
}

export function writeLastGroup(id: number): void {
  try {
    localStorage.setItem(LAST_GROUP_KEY, String(id));
  } catch {
    // without storage the app simply starts in the first group
  }
}
