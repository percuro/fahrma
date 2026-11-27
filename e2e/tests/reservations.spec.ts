import { expect, test } from '@playwright/test';
import { confirmDialog, createGroupWithCar, today } from './helpers';

const addDays = (day: string, n: number) => {
  const date = new Date(`${day}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + n);
  return date.toISOString().slice(0, 10);
};

test('reserve a car, see the clash, change and cancel it', async ({ page, request }) => {
  const { group, car } = await createGroupWithCar(request);
  const base = `/api/v1/groups/${group.id}`;
  // Next Monday: both reservations (Monday and Tuesday) are in the future and in the same calendar week
  const now = await today(request);
  const day = addDays(now, 7 - ((new Date(`${now}T00:00:00Z`).getUTCDay() + 6) % 7));
  const added = await request.post(`${base}/members`, { data: { display_name: 'Oma' } });
  expect(added.status(), await added.text()).toBe(201);
  const oma = ((await added.json()) as typeof group).members.find((m) => m.display_name === 'Oma')!.user_id;
  const omas = await request.post(`${base}/reservations`, {
    data: { car_id: car.id, user_id: oma, starts_at: `${addDays(day, 1)}T10:00`, ends_at: `${addDays(day, 1)}T12:00` },
  });
  expect(omas.status(), await omas.text()).toBe(201);

  await page.goto(`/g/${group.id}`);
  await page.getByRole('navigation', { name: 'Bereiche' }).getByRole('link', { name: 'Kalender' }).click();
  await expect(page.getByRole('heading', { name: 'Kalender' })).toBeVisible();

  // A new reservation
  await page.getByRole('link', { name: 'Reservieren' }).first().click();
  await expect(page.getByRole('heading', { name: 'Auto reservieren' })).toBeVisible();
  await page.getByLabel('Von', { exact: true }).fill(day);
  await page.getByLabel('Uhrzeit').first().fill('10:00');
  await page.getByLabel('Bis', { exact: true }).fill(day);
  await page.getByLabel('Uhrzeit').last().fill('12:00');
  await page.getByLabel('Notiz').fill('Baumarkt');
  await page.getByRole('button', { name: 'Speichern' }).click();
  await expect(page.getByRole('heading', { name: 'Kalender' })).toBeVisible();
  const mine = page.getByRole('link', { name: /10:00–12:00 · Baumarkt/ });
  await expect(mine).toBeVisible();

  // Oma has the car the next day: the clash names her
  await page.getByRole('link', { name: 'Reservieren' }).first().click();
  await page.getByLabel('Von', { exact: true }).fill(addDays(day, 1));
  await page.getByLabel('Uhrzeit').first().fill('11:00');
  await page.getByLabel('Bis', { exact: true }).fill(addDays(day, 1));
  await page.getByLabel('Uhrzeit').last().fill('13:00');
  await page.getByRole('button', { name: 'Speichern' }).click();
  await expect(page.getByRole('alert')).toContainText('Das Auto ist dann schon reserviert: Oma');
  await page.getByRole('button', { name: 'Abbrechen' }).click();

  // Longer, then cancelled
  await page.getByRole('link', { name: /10:00–12:00 · Baumarkt/ }).click();
  await expect(page.getByRole('heading', { name: 'Reservierung' })).toBeVisible();
  await page.getByLabel('Uhrzeit').last().fill('13:00');
  await page.getByRole('button', { name: 'Speichern' }).click();
  await expect(page.getByRole('link', { name: /10:00–13:00 · Baumarkt/ })).toBeVisible();
  await page.getByRole('link', { name: /10:00–13:00 · Baumarkt/ }).click();
  await page.getByRole('button', { name: 'Löschen' }).click();
  await confirmDialog(page, 'Löschen');
  await expect(page.getByRole('heading', { name: 'Kalender' })).toBeVisible();
  await expect(page.getByRole('link', { name: /Baumarkt/ })).toHaveCount(0);
  await expect(page.getByRole('link', { name: /Oma/ })).toBeVisible();
});

test('starting a trip shows who has the car reserved right now', async ({ page, request }) => {
  const { group, car } = await createGroupWithCar(request);
  const base = `/api/v1/groups/${group.id}`;
  const added = await request.post(`${base}/members`, { data: { display_name: 'Nachbar' } });
  const neighbour = ((await added.json()) as typeof group).members.find((m) => m.display_name === 'Nachbar')!.user_id;
  const hour = 3_600_000;
  const response = await request.post(`${base}/reservations`, {
    data: {
      car_id: car.id,
      user_id: neighbour,
      starts_at: new Date(Date.now() - hour).toISOString(),
      ends_at: new Date(Date.now() + hour).toISOString(),
    },
  });
  expect(response.status(), await response.text()).toBe(201);

  await page.goto(`/g/${group.id}`);
  const upcoming = page.locator('section').filter({ has: page.getByRole('heading', { name: 'Reservierungen' }) });
  await expect(upcoming.getByRole('link', { name: /Nachbar.*jetzt/ })).toBeVisible();
  await page.goto(`/g/${group.id}/trip/new`);
  await expect(page.getByRole('status').filter({ hasText: 'gerade für Nachbar reserviert' })).toBeVisible();
});
