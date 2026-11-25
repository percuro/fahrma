import { expect, test } from '@playwright/test';
import { confirmDialog, createGroupWithCar, joinByInvite } from './helpers';

test('switch the interface to English and back', async ({ page, request }) => {
  const { group } = await createGroupWithCar(request);
  await page.goto('/profile');
  await page.getByLabel('Sprache').selectOption('en');
  await page.getByRole('button', { name: 'Speichern' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Profile' })).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');

  await page.goto(`/g/${group.id}`);
  await expect(page.getByRole('link', { name: 'Trip', exact: true })).toBeVisible();
  await expect(page.getByRole('navigation', { name: 'Sections' })).toBeVisible();

  await page.goto('/profile');
  await page.getByLabel('Language').selectOption('');
  await page.getByRole('button', { name: 'Save' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Profil' })).toBeVisible();
});

test('electric car: charging entry with kWh and price per kWh', async ({ page, request }) => {
  const { group } = await createGroupWithCar(request, 'kWh');
  await page.goto(`/g/${group.id}`);
  await page.getByRole('link', { name: 'Laden' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Geladen' })).toBeVisible();
  await page.getByLabel(/Betrag/).fill('15');
  await page.getByLabel(/kWh/).fill('30');
  await expect(page.getByText(/0,500.*\/kWh/)).toBeVisible();
  await page.getByRole('button', { name: 'Speichern' }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Gespeichert' })).toBeVisible();

  await page.goto(`/g/${group.id}/history?tab=fuel`);
  await expect(page.getByRole('tabpanel')).toContainText('30 kWh');
});

test('group settings: currency and time zone', async ({ page, request }) => {
  const { group } = await createGroupWithCar(request);
  await page.goto(`/g/${group.id}/group`);
  await page.getByLabel('Währung').selectOption('CHF');
  await page.getByLabel('Zeitzone').selectOption('Europe/Zurich');
  await page.getByRole('button', { name: 'Speichern' }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Gespeichert' })).toBeVisible();

  await page.goto(`/g/${group.id}/fuel/new`);
  await expect(page.getByLabel(/Betrag CHF/)).toBeVisible();
});

test('history tabs work with the keyboard', async ({ page, request }) => {
  const { group } = await createGroupWithCar(request);
  await page.goto(`/g/${group.id}/history`);
  const trips = page.getByRole('tab', { name: 'Fahrten' });
  await trips.focus();
  await page.keyboard.press('ArrowRight');
  await expect(page.getByRole('tab', { name: 'Tanken/Laden' })).toBeFocused();
  await expect(page.getByRole('tab', { name: 'Tanken/Laden' })).toHaveAttribute('aria-selected', 'true');
  await page.keyboard.press('End');
  await expect(page.getByRole('tab', { name: 'Kosten' })).toHaveAttribute('aria-selected', 'true');
});

test('removing a member asks for confirmation', async ({ page, request, browser }) => {
  const { group } = await createGroupWithCar(request);
  const sam = await joinByInvite(browser, request, group.id, 'Sam');
  await sam.context.close();
  await page.goto(`/g/${group.id}/group`);
  const row = page.locator('li', { hasText: 'Sam' });
  await row.getByRole('button', { name: 'Austragen' }).click();
  await confirmDialog(page, 'Abbrechen');
  await expect(row).not.toContainText('ausgetreten');
  await row.getByRole('button', { name: 'Austragen' }).click();
  await confirmDialog(page, 'Austragen');
  await expect(row).toContainText('ausgetreten');
});
