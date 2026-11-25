import { expect, type APIRequestContext, type Browser, type Page } from '@playwright/test';

export interface Group {
  id: number;
  name: string;
  members: { user_id: number; display_name: string }[];
}

let counter = 0;

/** Unique name per test run, so tests never see each other's data. */
export function uniqueName(prefix: string): string {
  counter += 1;
  return `${prefix} ${Date.now().toString(36)}${counter}`;
}

async function created<T>(response: Awaited<ReturnType<APIRequestContext['post']>>): Promise<T> {
  expect(response.status(), await response.text()).toBe(201);
  return (await response.json()) as T;
}

/** A new group with one car starting at km 10,000; the e2e account is its admin. */
export async function createGroupWithCar(request: APIRequestContext, energyUnit: 'l' | 'kWh' = 'l') {
  const group = await created<Group>(await request.post('/api/v1/groups', { data: { name: uniqueName('Gruppe') } }));
  const car = await created<{ id: number; name: string }>(
    await request.post(`/api/v1/groups/${group.id}/cars`, {
      data: { name: 'Testauto', plate: 'T-1', start_odometer_km: 10000, energy_unit: energyUnit },
    }),
  );
  return { group, car, me: group.members[0].user_id };
}

export async function today(request: APIRequestContext): Promise<string> {
  const response = await request.get('/api/v1/auth/me');
  return ((await response.json()) as { today: string }).today;
}

/** Registers a second person through the invitation page in a separate browser context. */
export async function joinByInvite(browser: Browser, request: APIRequestContext, groupId: number, name: string) {
  const invite = await created<{ url: string; token: string }>(
    await request.post(`/api/v1/groups/${groupId}/invites`),
  );
  const context = await browser.newContext({ storageState: { cookies: [], origins: [] } });
  const page = await context.newPage();
  await page.goto(`/invite/${invite.token}`);
  await page.getByLabel('Dein Name').fill(name);
  await page.getByLabel('Benutzername').fill(uniqueName('user').replace(' ', '-'));
  await page.getByLabel('Passwort (mind. 12 Zeichen)').fill('e2e-password-456');
  await page.getByLabel('Passwort wiederholen').fill('e2e-password-456');
  await page.getByRole('button', { name: 'Zugang anlegen und beitreten' }).click();
  await expect(page.getByRole('navigation', { name: 'Bereiche' })).toBeVisible();
  return { context, page };
}

/** Confirms the app's own confirmation dialog (it replaces window.confirm). */
export async function confirmDialog(page: Page, button: string | RegExp) {
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  await dialog.getByRole('button', { name: button }).click();
  await expect(dialog).toBeHidden();
}
