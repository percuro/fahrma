import { expect, test, type APIRequestContext, type Browser, type Page } from '@playwright/test';
import { anonymousPage, createGroupWithCar, groupInvite, joinByInvite, OTHER_PASSWORD, uniqueUsername } from './helpers';

/** Set by CI (and local runs) when Dex runs next to the instance; see e2e/oidc/dex.yaml. */
const OIDC = process.env.E2E_OIDC === '1';
const ADMIN_PASSWORD = process.env.E2E_PASSWORD ?? 'e2e-password-123';
const DEX_PASSWORD = 'password';

/** Log in on Dex's own page; the browser then returns to fahrma. */
async function dexLogin(page: Page, email: string) {
  await page.locator('#login').fill(email);
  await page.locator('#password').fill(DEX_PASSWORD);
  await page.locator('#submit-login').click();
}

/**
 * Both projects (chromium, webkit) run the same tests against the same Dex users:
 * remove accounts that earlier runs linked, and the e2e account's own link.
 */
async function forgetProviderAccounts(admin: APIRequestContext) {
  const me = (await (await admin.get('/api/v1/auth/me')).json()) as { id: number };
  const users = (await (await admin.get('/api/v1/admin/users')).json()) as { id: number; oidc_linked?: boolean }[];
  for (const user of users.filter((u) => u.oidc_linked)) {
    const response = user.id === me.id
      ? await admin.delete('/api/v1/account/oidc', { data: { password: ADMIN_PASSWORD } })
      : await admin.delete(`/api/v1/admin/users/${user.id}`);
    expect(response.status(), await response.text()).toBe(204);
  }
}

function signInSection(page: Page) {
  return page.locator('details', { has: page.getByRole('heading', { name: 'Anmeldung', exact: true }) });
}

async function joinWithDex(browser: Browser, request: APIRequestContext, email: string) {
  const { group } = await createGroupWithCar(request);
  const invite = await groupInvite(request, group.id);
  const { context, page } = await anonymousPage(browser);
  const username = uniqueUsername();
  await page.goto(invite.url);
  await page.getByLabel('Dein Name').fill('Anna');
  await page.getByLabel('Benutzername').fill(username);
  await page.getByRole('button', { name: 'Weiter mit Dex' }).click();
  await dexLogin(page, email);
  await expect(page.getByRole('navigation', { name: 'Bereiche' })).toBeVisible();
  return { context, page, username };
}

test.describe('login through OIDC (Dex)', () => {
  test.skip(!OIDC, 'needs Dex: set E2E_OIDC=1');

  test.beforeEach(async ({ request }) => {
    await forgetProviderAccounts(request);
  });

  test('an invited person joins and logs in again with the provider', async ({ browser, request }) => {
    const { context, page, username } = await joinWithDex(browser, request, 'anna@example.org');
    await page.goto('/profile');
    await expect(page.getByText(`Angemeldet als @${username}`)).toBeVisible();
    await expect(signInSection(page).getByText('Verknüpft mit Dex als anna@example.org.')).toBeVisible();
    // No password yet: the account can set one, without a current password
    await expect(page.getByRole('heading', { name: 'Passwort festlegen' })).toBeVisible();
    await expect(page.getByLabel('Aktuelles Passwort')).toHaveCount(0);

    await page.getByRole('button', { name: 'Abmelden', exact: true }).click();
    await page.getByRole('dialog').getByRole('button', { name: 'Abmelden' }).click();
    await page.getByRole('button', { name: 'Anmelden mit Dex' }).click();
    await dexLogin(page, 'anna@example.org');
    await expect(page.getByRole('link', { name: 'Profil' })).toBeVisible();
    await context.close();
  });

  test('the e2e account links and unlinks the provider', async ({ page }) => {
    await page.goto('/profile');
    const section = signInSection(page);
    await section.getByRole('heading', { name: 'Anmeldung' }).click();
    await section.getByLabel('Dein Passwort zum Verknüpfen').fill(ADMIN_PASSWORD);
    await section.getByRole('button', { name: 'Mit Dex verknüpfen' }).click();
    await dexLogin(page, 'ben@example.org');
    await expect(page.getByRole('status').filter({ hasText: 'jetzt mit Dex verknüpft' })).toBeVisible();
    await expect(section.getByText('Verknüpft mit Dex als ben@example.org.')).toBeVisible();

    await page.goto('/admin');
    await expect(page.getByText('meldet sich mit Dex an').first()).toBeVisible();

    await page.goto('/profile');
    await section.getByLabel('Dein Passwort zur Bestätigung').fill(ADMIN_PASSWORD);
    await section.getByRole('button', { name: 'Verknüpfung entfernen' }).click();
    await page.getByRole('dialog').getByRole('button', { name: 'Verknüpfung entfernen' }).click();
    await expect(section.getByText('dann kannst du dich auch dort anmelden')).toBeVisible();
  });

  test('a provider account without an account here gets a clear message', async ({ browser }) => {
    const { context, page } = await anonymousPage(browser);
    await page.goto('/');
    await page.getByRole('button', { name: 'Anmelden mit Dex' }).click();
    await dexLogin(page, 'carla@example.org');
    await expect(page.getByRole('alert')).toContainText('gibt es hier noch keinen Zugang');
    await context.close();
  });

  test('registering with the provider needs the terms', async ({ browser }) => {
    const { context, page } = await anonymousPage(browser);
    await page.goto('/register');
    await page.getByRole('button', { name: 'Registrieren mit Dex' }).click();
    await expect(page.getByRole('alert')).toContainText('Nutzungsbedingungen');
    await page.getByRole('checkbox').check();
    await page.getByRole('button', { name: 'Registrieren mit Dex' }).click();
    await dexLogin(page, 'carla@example.org');
    await expect(page.getByRole('link', { name: 'Profil' })).toBeVisible();
    await context.close();
  });
  test('a linked account removes its password and then needs the provider', async ({ browser, request }) => {
    const { group } = await createGroupWithCar(request);
    const { context, page, username } = await joinByInvite(browser, request, group.id, 'Ben');
    await page.goto('/profile');
    const section = signInSection(page);
    await section.getByRole('heading', { name: 'Anmeldung' }).click();
    await section.getByLabel('Dein Passwort zum Verknüpfen').fill(OTHER_PASSWORD);
    await section.getByRole('button', { name: 'Mit Dex verknüpfen' }).click();
    await dexLogin(page, 'ben@example.org');
    await expect(section.getByText('Verknüpft mit Dex als ben@example.org.')).toBeVisible();

    // Logged in with the password: the provider has to confirm first
    await section.getByRole('button', { name: 'Passwort entfernen' }).click();
    await page.getByRole('dialog').getByRole('button', { name: 'Passwort entfernen' }).click();
    await section.getByRole('button', { name: 'Mit Dex bestätigen' }).click();
    await dexLogin(page, 'ben@example.org');
    await expect(page.getByRole('status').filter({ hasText: 'Bestätigt' })).toBeVisible();
    await section.getByRole('button', { name: 'Passwort entfernen' }).click();
    await page.getByRole('dialog').getByRole('button', { name: 'Passwort entfernen' }).click();
    await expect(page.getByRole('status').filter({ hasText: 'Passwort entfernt' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Passwort festlegen' })).toBeVisible();

    // The password no longer opens the account
    const other = await anonymousPage(browser);
    await other.page.goto('/');
    await other.page.getByLabel('Benutzername').fill(username);
    await other.page.getByLabel('Passwort').fill(OTHER_PASSWORD);
    await other.page.getByRole('button', { name: 'Anmelden', exact: true }).click();
    await expect(other.page.getByRole('alert')).toContainText('falsch');
    await other.context.close();
    await context.close();
  });
});
