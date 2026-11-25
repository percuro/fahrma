import { expect, test } from '@playwright/test';
import { confirmDialog, createGroupWithCar, joinByInvite } from './helpers';

test('two people: trip, fuel, settle and mark the transfer as paid', async ({ page, request, browser }) => {
  const { group } = await createGroupWithCar(request);
  const sam = await joinByInvite(browser, request, group.id, 'Sam');

  // Sam pays for fuel
  await sam.page.getByRole('link', { name: 'Tanken' }).click();
  await sam.page.getByLabel('Betrag €').fill('60');
  await sam.page.getByLabel('Liter').fill('40');
  await sam.page.getByRole('button', { name: 'Speichern' }).click();
  await expect(sam.page.getByRole('heading', { level: 1, name: group.name })).toBeVisible();

  // The admin drives 200 km alone
  await page.goto(`/g/${group.id}`);
  await page.getByRole('link', { name: 'Fahrt', exact: true }).click();
  await expect(page.getByLabel('km-Stand Start')).toHaveValue('10000');
  await page.getByLabel('km-Stand Ende').fill('10200');
  await page.getByRole('button', { name: 'Speichern' }).click();
  await expect(page.getByRole('heading', { level: 1, name: group.name })).toBeVisible();

  // Settle: the admin owes Sam the full 60 €
  await page.getByRole('navigation', { name: 'Bereiche' }).getByRole('link', { name: 'Abrechnung' }).click();
  await expect(page.getByRole('cell', { name: /0,300.*\/km/ })).toBeVisible();
  await page.getByRole('button', { name: 'Jetzt abrechnen' }).click();
  await confirmDialog(page, 'Jetzt abrechnen');
  await expect(page.getByRole('heading', { level: 1, name: /^Abrechnung/ })).toBeVisible();
  const transfer = page.locator('li', { hasText: '→ Sam' });
  await expect(transfer).toContainText('60,00');

  await transfer.getByRole('button', { name: 'Bezahlt' }).click();
  await expect(transfer).toContainText('bezahlt am');
  await expect(transfer.getByRole('button', { name: 'Rückgängig' })).toBeVisible();

  // Settled entries are read-only for everyone
  await sam.page.reload();
  await expect(sam.page.getByText('Offene Überweisungen')).toHaveCount(0);
  await sam.context.close();
});
