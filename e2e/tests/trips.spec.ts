import { expect, test } from '@playwright/test';
import { createGroupWithCar, groupInvite } from './helpers';

test('start a trip now and finish it later from the overview', async ({ page, request }) => {
  const { group } = await createGroupWithCar(request);
  await page.goto(`/g/${group.id}`);
  await page.getByRole('link', { name: 'Fahrt', exact: true }).click();
  await page.getByRole('button', { name: 'Fahrt starten' }).click();

  const running = page.locator('form', { hasText: 'ist unterwegs' });
  await expect(running).toBeVisible();
  await running.getByLabel('km-Stand jetzt').fill('10042');
  await running.getByRole('button', { name: /Fahrt beenden \(42 km\)/ }).click();
  await expect(running).toHaveCount(0);
  await expect(page.getByRole('link', { name: /10\.000 – 10\.042|42 km/ }).first()).toBeVisible();
});

test('server errors are shown in German', async ({ page, request }) => {
  const { group, car, me } = await createGroupWithCar(request);
  const response = await request.post(`/api/v1/groups/${group.id}/trips`, {
    data: {
      car_id: car.id,
      date: '2026-01-10',
      start_km: 10000,
      end_km: 10100,
      shares: [{ user_id: me, weight: 1 }],
    },
  });
  expect(response.status()).toBe(201);

  await page.goto(`/g/${group.id}/trip/new`);
  await page.getByLabel('km-Stand Start').fill('10050');
  await page.getByLabel('km-Stand Ende').fill('10150');
  await page.getByRole('button', { name: 'Speichern' }).click();
  await expect(page.getByRole('alert')).toHaveText(
    'Überschneidet sich mit der Fahrt 10.000 km – 10.100 km vom 10.01.2026.',
  );
});

test('paths of earlier versions redirect', async ({ page, request }) => {
  const { group } = await createGroupWithCar(request);
  await page.goto(`/g/${group.id}/fahrt/neu`);
  await expect(page).toHaveURL(new RegExp(`/g/${group.id}/trip/new$`));
  await page.goto(`/g/${group.id}/verlauf?tab=tanken`);
  await expect(page).toHaveURL(new RegExp(`/g/${group.id}/history\\?tab=fuel$`));
  await expect(page.getByRole('tab', { name: 'Tanken/Laden' })).toHaveAttribute('aria-selected', 'true');
});

test('invitation links with the token in the path still work', async ({ page, request }) => {
  const { group } = await createGroupWithCar(request);
  const invite = await groupInvite(request, group.id);
  const token = invite.url.split('#')[1];
  for (const path of [`/einladung/${token}`, `/invite/${token}`]) {
    await page.goto(path);
    await expect(page).toHaveURL(new RegExp(`/invite#${token}$`));
    await expect(page.getByRole('heading', { name: 'Einladung' })).toBeVisible();
  }
});

test('an expired session keeps the input: log in again and save', async ({ page, request, context }) => {
  const { group } = await createGroupWithCar(request);
  await page.goto(`/g/${group.id}/trip/new`);
  await page.getByLabel('km-Stand Ende').fill('10077');
  await page.getByLabel(/Notiz/).fill('kept after login');
  const cookies = await context.cookies();
  await context.clearCookies();

  await page.getByRole('button', { name: 'Speichern' }).click();
  await expect(page.getByText('Deine Sitzung ist abgelaufen')).toBeVisible();
  await page.getByLabel('Benutzername').fill(process.env.E2E_USERNAME ?? 'e2e');
  await page.getByLabel('Passwort').fill(process.env.E2E_PASSWORD ?? 'e2e-password-123');
  await page.getByRole('button', { name: 'Anmelden', exact: true }).click();

  await expect(page.getByLabel('km-Stand Ende')).toHaveValue('10077');
  await expect(page.getByLabel(/Notiz/)).toHaveValue('kept after login');
  await page.getByRole('button', { name: 'Speichern' }).click();
  await expect(page.getByRole('heading', { level: 1, name: group.name })).toBeVisible();
  // The stored session of the other tests stays valid
  await context.addCookies(cookies);
});
