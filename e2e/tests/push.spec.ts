import { expect, test } from '@playwright/test';
import { createGroupWithCar, fakePushSubscription, joinByInvite, PUSH_DIR, pushesTo, today } from './helpers';

const DEFAULTS = { reservation_reminder: true, lead_minutes: 60, reservation_changes: true, open_trip: true, settlements: true };

test('choose which notifications to get', async ({ page, request }) => {
  // The e2e account is shared by all tests (and runs): start from the defaults
  expect((await request.put('/api/v1/account/notifications', { data: DEFAULTS })).status()).toBe(200);
  await page.goto('/profile');
  const section = page.locator('section').filter({ has: page.getByRole('heading', { name: 'Benachrichtigungen' }) });
  await expect(section.getByLabel('Auf diesem Gerät')).not.toBeChecked();
  await section.getByLabel('Bei einer neuen Abrechnung').uncheck();
  await expect(page.getByRole('status').filter({ hasText: 'Gespeichert' })).toBeVisible();
  await section.getByLabel('Vorlauf').selectOption({ label: '15 Minuten' });
  await page.reload();
  await expect(section.getByLabel('Bei einer neuen Abrechnung')).not.toBeChecked();
  await expect(section.getByLabel('Vorlauf')).toHaveValue('15');
  expect((await request.put('/api/v1/account/notifications', { data: DEFAULTS })).status()).toBe(200);
});

test('a reservation for someone else reaches their device', async ({ browser, request }) => {
  test.skip(!PUSH_DIR, 'needs an instance with PUSH_DIR (E2E_PUSH_DIR)');
  const { group, car } = await createGroupWithCar(request);
  const bea = await joinByInvite(browser, request, group.id, 'Bea');
  const device = fakePushSubscription('bea');
  const base = process.env.E2E_BASE_URL ?? 'http://localhost:8000';
  const headers = { 'X-Carshare-CSRF': '1', Origin: base };
  const subscribed = await bea.context.request.post(`${base}/api/v1/account/push-subscription`, { data: device, headers });
  expect(subscribed.status(), await subscribed.text()).toBe(200);
  const beaId = (await (await bea.context.request.get(`${base}/api/v1/auth/me`)).json()).id as number;

  const day = new Date(`${await today(request)}T00:00:00Z`);
  day.setUTCDate(day.getUTCDate() + 3);
  const date = day.toISOString().slice(0, 10);
  const reserved = await request.post(`/api/v1/groups/${group.id}/reservations`, {
    data: { car_id: car.id, user_id: beaId, starts_at: `${date}T09:00`, ends_at: `${date}T11:00` },
  });
  expect(reserved.status(), await reserved.text()).toBe(201);
  await expect.poll(() => pushesTo(device.endpoint).length, { timeout: 10_000 }).toBe(1);
  const [message] = pushesTo(device.endpoint);
  expect(message.title).toBe('Reservierung für dich');
  expect(message.body).toContain('Testauto für dich reserviert');
  expect(message.url).toMatch(new RegExp(`^/g/${group.id}/reservation/\\d+$`));

  // Bea sees this device switched on and can send a test
  await bea.page.goto('/profile');
  await expect(bea.page.getByLabel('Auf diesem Gerät')).toBeChecked();
  await bea.page.getByRole('button', { name: 'Test senden' }).click();
  await expect.poll(() => pushesTo(device.endpoint).length, { timeout: 10_000 }).toBe(2);
  expect(pushesTo(device.endpoint)[1].title).toBe('Benachrichtigungen funktionieren');
  await bea.context.close();
});
