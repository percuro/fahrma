import { expect, test, type Page } from '@playwright/test';
import {
  OTHER_PASSWORD,
  anonymousPage,
  confirmDialog,
  createGroupWithCar,
  fillAccount,
  joinByInvite,
  MAIL_DIR,
  nextMail,
  uniqueEmail,
  uniqueName,
  uniqueUsername,
} from './helpers';

/** A collapsible card on the profile page, found by its heading. */
function card(page: Page, heading: string) {
  return page.locator('details', { has: page.getByRole('heading', { name: heading }) });
}

test('change the password, see the devices, log in with the new password', async ({ browser, request }) => {
  const { group } = await createGroupWithCar(request);
  const { context, page, username } = await joinByInvite(browser, request, group.id, 'Kim');
  await page.goto('/profile');
  await expect(page.getByRole('heading', { name: 'Angemeldete Geräte' })).toBeVisible();
  await expect(page.getByText('dieses Gerät')).toBeVisible();

  const password = card(page, 'Passwort ändern');
  await password.getByText('Passwort ändern').click();
  await password.getByLabel('Aktuelles Passwort').fill(OTHER_PASSWORD);
  await password.getByLabel('Neues Passwort (mind. 12 Zeichen)').fill('another-password-789');
  await password.getByLabel('Passwort wiederholen').fill('another-password-789');
  await password.getByRole('button', { name: 'Speichern' }).click();
  await expect(page.getByText('Passwort geändert')).toBeVisible();
  await context.close();

  const fresh = await anonymousPage(browser);
  await fresh.page.goto('/');
  await fresh.page.getByLabel('Benutzername').fill(username);
  await fresh.page.getByLabel('Passwort').fill('another-password-789');
  await fresh.page.getByRole('button', { name: 'Anmelden' }).click();
  await expect(fresh.page.getByRole('navigation', { name: 'Bereiche' })).toBeVisible();
  await fresh.context.close();
});

test('delete the own account: bookings stay anonymously', async ({ browser, page, request }) => {
  const { group } = await createGroupWithCar(request);
  const other = await joinByInvite(browser, request, group.id, 'Sam');
  await other.page.goto('/profile');
  const zone = card(other.page, 'Zugang löschen');
  await zone.getByText('Zugang löschen').click();
  await zone.getByLabel('Zur Bestätigung dein Passwort').fill(OTHER_PASSWORD);
  await zone.getByRole('button', { name: 'Zugang endgültig löschen' }).click();
  await confirmDialog(other.page, 'Zugang endgültig löschen');
  await expect(other.page.getByRole('button', { name: 'Anmelden' })).toBeVisible();
  await other.context.close();

  await page.goto(`/g/${group.id}/group`);
  await expect(page.getByText('Zugang gelöscht')).toBeVisible();
  await expect(page.getByText('Sam', { exact: true })).toHaveCount(0);
});

test('admin: invitation link, password reset link, deactivate', async ({ browser, page, request }) => {
  const { group } = await createGroupWithCar(request);
  const other = await joinByInvite(browser, request, group.id, 'Alex');
  await other.context.close();

  await page.goto('/profile');
  await page.getByRole('link', { name: 'Verwaltung der Instanz' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Verwaltung der Instanz' })).toBeVisible();

  // Invitation to the instance: create, use in a fresh browser
  const note = uniqueName('für');
  await page.getByLabel('Notiz (z. B. für wen)').fill(note);
  await page.getByRole('button', { name: 'Einladungslink erstellen' }).click();
  await expect(page.getByText(note)).toBeVisible();
  const url = await page.locator('input[readonly]').first().inputValue();
  const invited = await anonymousPage(browser);
  await invited.page.goto(url);
  await expect(invited.page.getByRole('heading', { name: 'Zugang anlegen' })).toBeVisible();
  await fillAccount(invited.page, 'Robin', uniqueUsername());
  await invited.page.getByRole('button', { name: 'Zugang anlegen' }).click();
  await expect(invited.page.getByRole('heading', { name: 'Willkommen' })).toBeVisible();
  await invited.context.close();

  // Password reset for Alex
  const row = page.getByRole('listitem').filter({ hasText: other.username });
  await row.getByRole('button', { name: 'Link zum Zurücksetzen' }).click();
  await expect(page.getByText(`Link für @${other.username}`)).toBeVisible();
  const resetUrl = await page.locator('input[readonly]').first().inputValue();
  const reset = await anonymousPage(browser);
  await reset.page.goto(resetUrl);
  await reset.page.getByLabel('Neues Passwort (mind. 12 Zeichen)').fill('reset-password-321');
  await reset.page.getByLabel('Passwort wiederholen').fill('reset-password-321');
  await reset.page.getByRole('button', { name: 'Passwort setzen' }).click();
  await expect(reset.page.getByRole('navigation', { name: 'Bereiche' })).toBeVisible();

  // Deactivating logs Alex out everywhere
  await row.getByRole('button', { name: 'Deaktivieren' }).click();
  await confirmDialog(page, 'Deaktivieren');
  await expect(row.getByText('deaktiviert')).toBeVisible();
  await reset.page.reload();
  await expect(reset.page.getByRole('button', { name: 'Anmelden' })).toBeVisible();
  await reset.context.close();
});

test('delete a group after typing its name', async ({ page, request }) => {
  const { group } = await createGroupWithCar(request);
  await page.goto(`/g/${group.id}/group`);
  const zone = page.locator('details', { has: page.getByRole('heading', { name: 'Gruppe löschen' }) });
  await zone.getByText('Gruppe löschen').click();
  const submit = zone.getByRole('button', { name: 'Gruppe endgültig löschen' });
  await expect(submit).toBeDisabled();
  await zone.getByLabel(/Zur Bestätigung den Namen eingeben/).fill(group.name);
  await submit.click();
  await expect(page.getByText('Gruppe gelöscht')).toBeVisible();
  expect((await request.get(`/api/v1/groups/${group.id}`)).status()).toBe(404);
});

test('open registration with terms, operator links on the login page', async ({ browser, request }) => {
  const meta = (await (await request.get('/api/v1/meta')).json()) as {
    registration: string;
    mail: boolean;
    links: { terms_url: string | null };
  };
  test.skip(meta.registration !== 'open', 'instance runs with REGISTRATION=invite');
  test.skip(meta.mail && !MAIL_DIR, 'the instance sends mail, but E2E_MAIL_DIR is not set');
  const { context, page } = await anonymousPage(browser);
  await page.goto('/');
  if (meta.links.terms_url) await expect(page.getByRole('link', { name: 'Nutzungsbedingungen' })).toBeVisible();
  await page.getByRole('link', { name: 'Registrieren' }).click();
  await fillAccount(page, 'Neu', uniqueUsername());
  const email = uniqueEmail();
  if (meta.mail) await page.getByLabel(/E-Mail-Adresse/).fill(email);
  if (meta.links.terms_url) await page.getByLabel(/Ich akzeptiere/).check();
  await page.getByRole('button', { name: 'Zugang anlegen' }).click();
  if (meta.mail) {
    // The account only exists once the link in the mail is used
    await expect(page.getByRole('heading', { name: 'Fast geschafft' })).toBeVisible();
    const mail = await nextMail(email);
    await page.goto(mail.link!);
    await page.getByRole('button', { name: 'Zugang anlegen' }).click();
  }
  await expect(page.getByRole('heading', { name: 'Willkommen' })).toBeVisible();
  await context.close();
});
