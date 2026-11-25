import { expect, test } from '@playwright/test';
import {
  MAIL_DIR,
  OTHER_PASSWORD,
  anonymousPage,
  createGroupWithCar,
  joinByInvite,
  nextMail,
  uniqueEmail,
} from './helpers';

// Needs an instance that writes its mails to a directory the tests can read
test.skip(!MAIL_DIR, 'E2E_MAIL_DIR is not set');

test('confirm an e-mail address, then get a new password by mail', async ({ browser, request }) => {
  const { group } = await createGroupWithCar(request);
  const { context, page, username } = await joinByInvite(browser, request, group.id, 'Kim');
  const email = uniqueEmail();
  await page.goto('/profile');
  const card = page.locator('details', { has: page.getByRole('heading', { name: 'E-Mail-Adresse' }) });
  await card.getByText('E-Mail-Adresse').first().click();
  await card.getByLabel('Neue Adresse').fill(email);
  await card.getByLabel('Dein Passwort zur Bestätigung').fill(OTHER_PASSWORD);
  await card.getByRole('button', { name: 'Bestätigungslink schicken' }).click();
  await expect(card.getByText(`Wartet auf Bestätigung: ${email}`)).toBeVisible();

  const confirmation = await nextMail(email);
  expect(confirmation.subject).toContain('bestätigen');
  await page.goto(confirmation.link!);
  await page.getByRole('button', { name: 'Ja, Adresse bestätigen' }).click();
  await expect(page.getByText(`${email} ist jetzt bestätigt`)).toBeVisible();
  await page.goto('/profile');
  await card.getByText('E-Mail-Adresse').first().click();
  await expect(card.getByText(`Bestätigt: ${email}`)).toBeVisible();
  await context.close();

  const fresh = await anonymousPage(browser);
  await fresh.page.goto('/');
  await fresh.page.getByRole('link', { name: 'Passwort vergessen?' }).click();
  await fresh.page.getByLabel('Benutzername oder E-Mail-Adresse').fill(email);
  await fresh.page.getByRole('button', { name: 'Link anfordern' }).click();
  await expect(fresh.page.getByText(/ist jetzt eine Nachricht unterwegs/)).toBeVisible();
  const reset = await nextMail(email, 1);
  expect(reset.body).toContain(username);
  await fresh.page.goto(reset.link!);
  await fresh.page.getByLabel('Neues Passwort (mind. 12 Zeichen)').fill('reset-by-mail-123');
  await fresh.page.getByLabel('Passwort wiederholen').fill('reset-by-mail-123');
  await fresh.page.getByRole('button', { name: 'Passwort setzen' }).click();
  await expect(fresh.page.getByRole('navigation', { name: 'Bereiche' })).toBeVisible();
  await fresh.context.close();
});

test('invite into a group by e-mail', async ({ browser, page, request }) => {
  const { group } = await createGroupWithCar(request);
  const email = uniqueEmail();
  await page.goto(`/g/${group.id}/group`);
  const invite = page.locator('section', { has: page.getByRole('heading', { name: 'Jemanden einladen' }) });
  await invite.getByLabel('Auch per E-Mail schicken an (optional)').fill(email);
  await invite.getByRole('button', { name: 'Einladungslink erstellen' }).click();
  await expect(invite.getByText(`An ${email} geschickt.`)).toBeVisible();
  const mail = await nextMail(email);
  expect(mail.subject).toContain(group.name);
  expect(mail.link).toBe(await invite.getByLabel('Einladungslink').inputValue());

  const other = await anonymousPage(browser);
  await other.page.goto(mail.link!);
  await expect(other.page.getByRole('heading', { name: new RegExp(group.name) })).toBeVisible();
  await other.context.close();
});
