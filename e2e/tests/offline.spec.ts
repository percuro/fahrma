import { expect, test, type Page } from '@playwright/test';
import { confirmDialog, createGroupWithCar, today } from './helpers';

const drafts = (page: Page) => page.locator('section', { has: page.getByRole('heading', { name: /noch nicht gesendet/i }) });

test('a trip saved without a connection is sent once the connection is back', async ({ page, request, context }) => {
  const { group } = await createGroupWithCar(request);
  await page.goto(`/g/${group.id}`);
  await expect(page.getByRole('heading', { name: group.name })).toBeVisible();

  await context.setOffline(true);
  await expect(page.getByText('Offline – neue Einträge bleiben auf diesem Gerät')).toBeVisible();
  await page.getByRole('link', { name: 'Fahrt', exact: true }).click();
  await page.getByLabel('km-Stand Ende').fill('10030');
  await page.getByRole('button', { name: 'Speichern' }).click();
  await expect(page.getByText('Auf diesem Gerät gespeichert')).toBeVisible();
  await expect(drafts(page)).toContainText('30 km');
  await expect(drafts(page)).toContainText('wartet');
  // The next trip starts where the draft ended
  await page.getByRole('link', { name: 'Fahrt', exact: true }).click();
  await expect(page.getByLabel('km-Stand Start')).toHaveValue('10030');
  await page.getByRole('button', { name: 'Abbrechen' }).click();

  await context.setOffline(false);
  await expect(page.getByText('Ein Entwurf wurde gesendet')).toBeVisible();
  await expect(drafts(page)).toHaveCount(0);
  const trips = await (await request.get(`/api/v1/groups/${group.id}/trips`)).json();
  expect(trips).toHaveLength(1);
  expect(trips[0].end_km).toBe(10030);
});

test('an answer lost on the way does not save the entry twice', async ({ page, request }) => {
  const { group } = await createGroupWithCar(request);
  await page.goto(`/g/${group.id}/fuel/new`);
  // The request reaches the server, the answer never arrives
  await page.route('**/api/v1/groups/*/fuel', async (route) => {
    await route.fetch();
    await route.abort('connectionreset');
  });
  await page.getByLabel(/Betrag/).fill('61,20');
  await page.getByRole('button', { name: 'Speichern' }).click();
  await expect(page.getByText('Auf diesem Gerät gespeichert')).toBeVisible();
  await expect(drafts(page)).toContainText('61,20');

  await page.unroute('**/api/v1/groups/*/fuel');
  await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
  await expect(page.getByText('Ein Entwurf wurde gesendet')).toBeVisible();
  await expect(drafts(page)).toHaveCount(0);
  const fuel = await (await request.get(`/api/v1/groups/${group.id}/fuel`)).json();
  expect(fuel).toHaveLength(1);
});

test('a draft the server refuses can be opened and discarded', async ({ page, request, context }) => {
  const { group, car, me } = await createGroupWithCar(request);
  await page.goto(`/g/${group.id}`);
  await expect(page.getByRole('heading', { name: group.name })).toBeVisible();

  await context.setOffline(true);
  await page.getByRole('link', { name: 'Fahrt', exact: true }).click();
  await page.getByLabel('km-Stand Ende').fill('10100');
  await page.getByRole('button', { name: 'Speichern' }).click();
  await expect(drafts(page)).toBeVisible();

  // Meanwhile someone else recorded the same kilometres
  const day = await today(request);
  await request.post(`/api/v1/groups/${group.id}/trips`, {
    data: { car_id: car.id, date: day, start_km: 10000, end_km: 10080, shares: [{ user_id: me, weight: 1 }] },
  });
  await context.setOffline(false);
  await expect(drafts(page)).toContainText('abgelehnt');
  await expect(drafts(page)).toContainText('Überschneidet sich mit der Fahrt');

  await drafts(page).getByRole('link').first().click();
  await expect(page.getByText(/Nicht angenommen: Überschneidet/)).toBeVisible();
  await page.getByRole('button', { name: 'Entwurf verwerfen' }).click();
  await confirmDialog(page, 'Entwurf verwerfen');
  await expect(page.getByText('Entwurf verworfen')).toBeVisible();
  await expect(drafts(page)).toHaveCount(0);
});

test('finishing a running trip works offline too', async ({ page, request, context }) => {
  const { group, car, me } = await createGroupWithCar(request);
  const trip = await (
    await request.post(`/api/v1/groups/${group.id}/trips`, {
      data: { car_id: car.id, date: await today(request), start_km: 10000, end_km: null, shares: [{ user_id: me, weight: 1 }] },
    })
  ).json();
  await page.goto(`/g/${group.id}`);
  const running = page.locator('form', { hasText: 'ist unterwegs' });
  await expect(running).toBeVisible();

  await context.setOffline(true);
  await running.getByLabel('km-Stand jetzt').fill('10055');
  await running.getByRole('button', { name: /Fahrt beenden/ }).click();
  await expect(running).toHaveCount(0);
  await expect(drafts(page)).toContainText('bei 10.055 km');

  await context.setOffline(false);
  await expect(page.getByText('Ein Entwurf wurde gesendet')).toBeVisible();
  const saved = await (await request.get(`/api/v1/groups/${group.id}/trips/${trip.id}`)).json();
  expect(saved.end_km).toBe(10055);
});

test('the app starts without a connection with the last known group', async ({ page, request, context }) => {
  const { group } = await createGroupWithCar(request);
  await page.goto(`/g/${group.id}`);
  await expect(page.getByRole('heading', { name: group.name })).toBeVisible();
  // The service worker has the app shell (it takes over from the next page load on),
  // the offline cache has group, cars and trips
  await page.evaluate(() => navigator.serviceWorker.ready);
  await page.reload();
  await expect.poll(() => page.evaluate(() => !!navigator.serviceWorker.controller)).toBe(true);
  await expect.poll(() => page.evaluate(() => localStorage.getItem('fahrma:cache')?.includes('/cars') ?? false)).toBe(true);

  await context.setOffline(true);
  await page.reload();
  await expect(page.getByRole('heading', { name: group.name })).toBeVisible();
  await expect(page.getByText('Keine Verbindung: der Stand wird angezeigt')).toBeVisible();
  await page.getByRole('link', { name: 'Fahrt', exact: true }).click();
  await page.getByLabel('km-Stand Ende').fill('10012');
  await page.getByRole('button', { name: 'Speichern' }).click();
  await expect(page.getByText('Auf diesem Gerät gespeichert')).toBeVisible();

  await context.setOffline(false);
  await expect(page.getByText('Ein Entwurf wurde gesendet')).toBeVisible();
  await expect(page.locator('.stats')).toBeVisible();
});
