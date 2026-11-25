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

export const OTHER_PASSWORD = 'e2e-password-456';

/** A one-time link of the group (PUBLIC_URL/invite#<token>). */
export async function groupInvite(request: APIRequestContext, groupId: number) {
  return created<{ url: string; expires_at: string }>(await request.post(`/api/v1/groups/${groupId}/invites`));
}

/** A fresh browser without the e2e account's session. */
export async function anonymousPage(browser: Browser) {
  const context = await browser.newContext({ storageState: { cookies: [], origins: [] }, locale: 'de-AT' });
  return { context, page: await context.newPage() };
}

/** Fills the account form of the invitation and registration pages. */
export async function fillAccount(page: Page, name: string, username: string) {
  await page.getByLabel('Dein Name').fill(name);
  await page.getByLabel('Benutzername').fill(username);
  await page.getByLabel('Passwort (mind. 12 Zeichen)').fill(OTHER_PASSWORD);
  await page.getByLabel('Passwort wiederholen').fill(OTHER_PASSWORD);
}

export function uniqueUsername(): string {
  return uniqueName('user').replace(' ', '-').toLowerCase();
}

/** Registers a second person through the invitation page in a separate browser context. */
export async function joinByInvite(browser: Browser, request: APIRequestContext, groupId: number, name: string) {
  const invite = await groupInvite(request, groupId);
  const { context, page } = await anonymousPage(browser);
  const username = uniqueUsername();
  await page.goto(invite.url);
  await fillAccount(page, name, username);
  await page.getByRole('button', { name: 'Zugang anlegen und beitreten' }).click();
  await expect(page.getByRole('navigation', { name: 'Bereiche' })).toBeVisible();
  return { context, page, username };
}

/** Confirms the app's own confirmation dialog (it replaces window.confirm). */
export async function confirmDialog(page: Page, button: string | RegExp) {
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  await dialog.getByRole('button', { name: button }).click();
  await expect(dialog).toBeHidden();
}
