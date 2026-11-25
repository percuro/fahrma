import { expect, test } from '@playwright/test';
import { createGroupWithCar, today } from './helpers';

test('statistics show distance, consumption and costs of a car', async ({ page, request }) => {
  const { group, car, me } = await createGroupWithCar(request);
  const day = await today(request);
  const base = `/api/v1/groups/${group.id}`;
  const shares = [{ user_id: me, weight: 1 }];
  for (const [start, end] of [[10000, 10400], [10400, 10800]]) {
    expect((await request.post(`${base}/trips`, { data: { car_id: car.id, date: day, start_km: start, end_km: end, shares } })).status()).toBe(201);
  }
  for (const [km, milli, cents] of [[10000, 40000, 6400], [10800, 48000, 7680]]) {
    const response = await request.post(`${base}/fuel`, {
      data: { car_id: car.id, date: day, odometer_km: km, quantity_milli: milli, amount_cents: cents, paid_by_user_id: me, full_tank: true },
    });
    expect(response.status()).toBe(201);
  }

  await page.goto(`/g/${group.id}`);
  await page.getByRole('link', { name: 'Statistik', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Statistik' })).toBeVisible();
  const tiles = page.locator('.stats');
  await expect(tiles).toContainText('800 km');
  await expect(tiles).toContainText('6,0 l/100 km'); // 48 l over 800 km, full to full
  await expect(tiles).toContainText(/1,600 ?€?\/l/);
  await expect(page.getByRole('img', { name: /Säulendiagramm/ })).toBeVisible();
  await expect(page.getByRole('table')).toContainText('140,80');

  await page.getByLabel('Zeitraum').selectOption('all');
  await expect(page).toHaveURL(/year=all/);
  await expect(page.getByRole('heading', { name: 'Kilometer je Jahr' })).toBeVisible();
});
