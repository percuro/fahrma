import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { expect, test } from '@playwright/test';
import { anonymousPage, createGroupWithCar, fillAccount, today, uniqueUsername, type Group } from './helpers';

interface Balance {
  members: { display_name: string; balance_cents: number }[];
}

const balances = (balance: Balance) =>
  Object.fromEntries(balance.members.map((m) => [m.display_name, m.balance_cents]));

test('people without an account, and taking over the place with a personal link', async ({ browser, page, request }) => {
  const { group, car, me } = await createGroupWithCar(request);
  await page.goto(`/g/${group.id}/group`);
  await page.getByText('Person ohne Zugang hinzufügen').click();
  await page.getByLabel('Name', { exact: true }).fill('Oma');
  await page.getByRole('button', { name: 'Hinzufügen' }).click();
  const row = page.getByRole('listitem').filter({ hasText: 'Oma' });
  await expect(row.getByText('ohne Zugang')).toBeVisible();

  // Others record trips for the person
  const members = ((await (await request.get(`/api/v1/groups/${group.id}`)).json()) as Group).members;
  const oma = members.find((m) => m.display_name === 'Oma')!.user_id;
  const day = await today(request);
  const trip = await request.post(`/api/v1/groups/${group.id}/trips`, {
    data: { car_id: car.id, date: day, start_km: 10000, end_km: 10100, shares: [{ user_id: oma, weight: 1 }], external: [] },
  });
  expect(trip.status()).toBe(201);
  await request.post(`/api/v1/groups/${group.id}/fuel`, {
    data: { car_id: car.id, date: day, amount_cents: 1000, paid_by_user_id: me, quantity_milli: 5000 },
  });
  const before = balances(await (await request.get(`/api/v1/groups/${group.id}/balance`)).json());

  await row.getByRole('button', { name: 'Link zum Übernehmen' }).click();
  await row.getByRole('button', { name: 'Einladungslink erstellen' }).click();
  const url = await row.getByLabel('Link zum Übernehmen').inputValue();
  await expect(row.getByText(/Link offen bis/)).toBeVisible();

  const other = await anonymousPage(browser);
  await other.page.goto(url);
  await expect(other.page.getByRole('heading', { name: /als Oma/ })).toBeVisible();
  await expect(other.page.getByLabel('Dein Name')).toHaveValue('Oma');
  const username = uniqueUsername();
  await fillAccount(other.page, 'Oma Erna', username);
  await other.page.getByRole('button', { name: 'Zugang anlegen und Platz übernehmen' }).click();
  await expect(other.page.getByRole('navigation', { name: 'Bereiche' })).toBeVisible();
  await other.context.close();

  await page.reload();
  const taken = page.getByRole('listitem').filter({ hasText: 'Oma Erna' });
  await expect(taken.getByText(`@${username}`)).toBeVisible();
  const after = balances(await (await request.get(`/api/v1/groups/${group.id}/balance`)).json());
  expect(after['Oma Erna']).toBe(before['Oma']);
});

test('move a group to another instance: export, import, same numbers', async ({ page, request }) => {
  const { group, car, me } = await createGroupWithCar(request);
  await request.post(`/api/v1/groups/${group.id}/members`, { data: { display_name: 'Sam' } });
  const sam = ((await (await request.get(`/api/v1/groups/${group.id}`)).json()) as Group).members.find(
    (m) => m.display_name === 'Sam',
  )!.user_id;
  const day = await today(request);
  for (const [start, end, who] of [[10000, 10100, me], [10100, 10400, sam]]) {
    await request.post(`/api/v1/groups/${group.id}/trips`, {
      data: { car_id: car.id, date: day, start_km: start, end_km: end, shares: [{ user_id: who, weight: 1 }], external: [] },
    });
  }
  await request.post(`/api/v1/groups/${group.id}/fuel`, {
    data: { car_id: car.id, date: day, amount_cents: 4000, paid_by_user_id: sam, quantity_milli: 20000 },
  });
  const settled = await request.post(`/api/v1/groups/${group.id}/settlements`, { data: { period_end: day } });
  expect(settled.status()).toBe(201);
  const settlementId = ((await settled.json()) as { id: number }).id;
  const before = balances((await (await request.get(`/api/v1/groups/${group.id}/settlements/${settlementId}`)).json()).result);

  const exported = await (await request.get(`/api/v1/groups/${group.id}/export.json`)).text();
  const file = join(mkdtempSync(join(tmpdir(), 'fahrma-')), 'group.json');
  writeFileSync(file, exported);

  await page.goto('/profile');
  await page.getByText('Weitere Fahrgemeinschaft anlegen').click();
  await page.getByRole('link', { name: 'Fahrgemeinschaft von einer anderen Instanz übernehmen' }).click();
  await page.getByLabel('Exportdatei (JSON)').setInputFiles(file);
  await expect(page.getByRole('heading', { name: group.name })).toBeVisible();
  await expect(page.getByText(/2 Fahrten · 1 Tank-\/Ladeeinträge/)).toBeVisible();
  // The e2e account is preselected by its name
  await expect(page.getByRole('radio', { name: /Erika/ })).toBeChecked();
  await page.getByRole('button', { name: 'Übernehmen' }).click();
  await expect(page.getByText('Fahrgemeinschaft übernommen')).toBeVisible();
  await expect(page.getByRole('heading', { level: 1, name: group.name })).toBeVisible();
  await expect(page.getByRole('listitem').filter({ hasText: 'Sam' }).getByText('ohne Zugang')).toBeVisible();

  const newId = Number(page.url().match(/\/g\/(\d+)\//)![1]);
  expect(newId).not.toBe(group.id);
  const list = (await (await request.get(`/api/v1/groups/${newId}/settlements`)).json()) as { id: number }[];
  const after = balances((await (await request.get(`/api/v1/groups/${newId}/settlements/${list[0].id}`)).json()).result);
  expect(after).toEqual(before);
});

test('a file that is not an export is rejected with a reason', async ({ page }) => {
  const file = join(mkdtempSync(join(tmpdir(), 'fahrma-')), 'other.json');
  writeFileSync(file, JSON.stringify({ format: 'fahrma-account/1' }));
  await page.goto('/import');
  await page.getByLabel('Exportdatei (JSON)').setInputFiles(file);
  await expect(page.getByRole('alert')).toContainText('fahrma-group/1');
  await expect(page.getByRole('button', { name: 'Übernehmen' })).toHaveCount(0);
});
