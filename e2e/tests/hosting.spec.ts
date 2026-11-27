import { expect, test } from '@playwright/test';
import { createGroupWithCar, today } from './helpers';

/**
 * Plans per group. Needs an instance with PLANS_FILE (plans "open" as default, without limits,
 * and "small" with one car and 1 MB for receipts) and BILLING_URL; otherwise skipped. See .github/workflows/ci.yml.
 */
test.beforeEach(async ({ request }) => {
  const meta = (await (await request.get('/api/v1/meta')).json()) as { plans: { id: string }[] | null; billing: boolean };
  test.skip(!meta.plans?.some((plan) => plan.id === 'small') || !meta.billing, 'instance without the test plans');
});

test('a group on a small plan: what it shows, what it refuses, where admins change it', async ({ page, request }) => {
  const { group } = await createGroupWithCar(request);
  const day = await today(request);
  const until = `${Number(day.slice(0, 4)) + 1}${day.slice(4)}`;
  const set = await request.put(`/api/v1/admin/groups/${group.id}/plan`, {
    data: { plan: 'small', until, note: 'E2E invoice' },
  });
  expect(set.status(), await set.text()).toBe(200);

  await page.goto(`/g/${group.id}/group`);
  const card = page.getByRole('region', { name: 'Tarif' });
  await expect(card).toContainText('Klein');
  await expect(card).toContainText(/gültig bis/);
  await expect(card.getByRole('listitem').filter({ hasText: 'Autos' })).toContainText('1 von 1 · voll');
  await expect(card.getByRole('listitem').filter({ hasText: 'Mitglieder' })).toContainText('1 von 3');
  await expect(card.getByRole('listitem').filter({ hasText: 'Speicher für Belege' })).toContainText('0 MB von 1 MB');
  // The operator's note stays in the administration
  await expect(page.getByText('E2E invoice')).toHaveCount(0);

  // A second car is beyond the plan
  await page.getByRole('button', { name: '+ Auto' }).click();
  const carName = page.getByRole('textbox', { name: 'Name', exact: true });
  const carForm = page.locator('form').filter({ has: carName });
  await carName.fill('Zweitauto');
  await carForm.getByLabel(/km-Stand zu Beginn/).fill('0');
  await carForm.getByRole('button', { name: 'Speichern' }).click();
  await expect(carForm.getByRole('alert')).toContainText('Der Tarif der Gruppe erlaubt höchstens 1 Autos');

  // Group admins go to the operator's page, with the group in the fragment
  await page.route('https://example.org/**', (route) => route.fulfill({ contentType: 'text/html', body: '<h1>Tarife</h1>' }));
  await page.getByRole('button', { name: 'Tarif ändern' }).click();
  await page.waitForURL(/^https:\/\/example\.org\/plans#/);
  expect(new URL(page.url()).hash).toBe(`#group=${group.id}&plan=small`);
});

test('instance admins see groups with their plan and change it', async ({ page, request }) => {
  const { group } = await createGroupWithCar(request);
  await page.goto('/admin?tab=groups');
  const section = page.getByRole('region', { name: 'Gruppen' });
  const row = section.getByRole('listitem').filter({ hasText: `#${group.id}` });
  await expect(row).toContainText('1 Mitglied · 1 Auto');
  await row.getByRole('button', { name: 'Tarif ändern' }).click();
  await row.getByRole('combobox', { name: 'Tarif' }).selectOption('small');
  await row.getByLabel(/Notiz/).fill('Rechnung 1');
  await row.getByRole('button', { name: 'Speichern' }).click();
  await expect(row).toContainText('Klein');
  await expect(row).toContainText('Rechnung 1');

  await page.goto(`/g/${group.id}/group`);
  await expect(page.getByRole('region', { name: 'Tarif' })).toContainText('Klein');
});
