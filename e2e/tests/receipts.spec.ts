import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';
import { confirmDialog, createGroupWithCar, today } from './helpers';

interface Receipt { id: number; width: number; height: number; content_type: string }

/** A real photo for the file input: a portrait PNG drawn in the page, shrunk by the app to a JPEG. */
async function photo(page: Page, width = 300, height = 400) {
  const base64 = await page.evaluate(([w, h]) => {
    const canvas = document.createElement('canvas');
    canvas.width = w;
    canvas.height = h;
    const context = canvas.getContext('2d')!;
    context.fillStyle = '#c33';
    context.fillRect(0, 0, w, h);
    context.fillStyle = '#fff';
    context.fillRect(10, 10, w / 2, h / 4);
    return canvas.toDataURL('image/png').split(',')[1];
  }, [width, height]);
  return { name: 'beleg.png', mimeType: 'image/png', buffer: Buffer.from(base64, 'base64') };
}

const receiptsOf = async (page: Page, url: string): Promise<Receipt[]> =>
  ((await (await page.request.get(url)).json()) as { receipts: Receipt[] }).receipts;

test('a fuel entry with a photo: attach, see large, delete', async ({ page, request }) => {
  const { group } = await createGroupWithCar(request);
  await page.goto(`/g/${group.id}/fuel/new`);
  await page.getByLabel(/Betrag/).fill('48,90');
  await page.getByTestId('receipt-library').setInputFiles(await photo(page));
  await expect(page.getByRole('button', { name: 'Beleg 1 ansehen' })).toBeVisible();
  await page.getByRole('button', { name: 'Speichern' }).click();
  await expect(page.getByText('Gespeichert', { exact: true })).toBeVisible();

  const fuel = (await (await request.get(`/api/v1/groups/${group.id}/fuel`)).json()) as { id: number; receipts: Receipt[] }[];
  expect(fuel).toHaveLength(1);
  expect(fuel[0].receipts.map((r) => [r.width, r.height, r.content_type])).toEqual([[300, 400, 'image/jpeg']]);

  // The history marks the entry; the entry shows the photo
  await page.goto(`/g/${group.id}/history?tab=fuel`);
  await expect(page.getByTitle('mit Beleg')).toBeVisible();
  await page.goto(`/g/${group.id}/fuel/${fuel[0].id}`);
  await page.getByRole('button', { name: 'Beleg 1 ansehen' }).click();
  const viewer = page.getByRole('dialog', { name: 'Beleg 1' });
  await expect(viewer.getByRole('img', { name: 'Beleg 1' })).toBeVisible();
  expect(await viewer.getByRole('img').evaluate((img: HTMLImageElement) => img.naturalWidth)).toBe(300);
  await viewer.getByRole('button', { name: 'Schließen' }).click();
  await expect(viewer).toBeHidden();

  await page.getByRole('button', { name: 'Beleg 1 entfernen' }).click();
  await confirmDialog(page, 'Löschen');
  await expect(page.getByText('Foto gelöscht')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Beleg 1 ansehen' })).toHaveCount(0);
  expect(await receiptsOf(page, `/api/v1/groups/${group.id}/fuel/${fuel[0].id}`)).toEqual([]);
});

test('a photo added to a saved expense goes straight to the server', async ({ page, request }) => {
  const { group, me } = await createGroupWithCar(request);
  const created = await request.post(`/api/v1/groups/${group.id}/expenses`, {
    data: { date: await today(request), category: 'repair', amount_cents: 32000, paid_by_user_id: me, allocation: 'equal' },
  });
  const expense = (await created.json()) as { id: number };
  await page.goto(`/g/${group.id}/expense/${expense.id}`);
  await page.getByTestId('receipt-camera').setInputFiles(await photo(page, 2400, 1800));
  await expect(page.getByRole('button', { name: 'Beleg 1 ansehen' })).toBeVisible();
  // Shrunk on the device: at most 1600 px on the longer side
  await expect.poll(async () => (await receiptsOf(page, `/api/v1/groups/${group.id}/expenses/${expense.id}`)).map((r) => [r.width, r.height]))
    .toEqual([[1600, 1200]]);
});

test('a photo taken without a connection goes with its draft', async ({ page, request, context }) => {
  const { group } = await createGroupWithCar(request);
  await page.goto(`/g/${group.id}/fuel/new`);
  const file = await photo(page);
  await expect(page.getByTestId('receipt-library')).toBeAttached();
  await context.setOffline(true);
  await page.getByLabel(/Betrag/).fill('22,00');
  await page.getByTestId('receipt-library').setInputFiles(file);
  await expect(page.getByRole('button', { name: 'Beleg 1 ansehen' })).toBeVisible();
  await page.getByRole('button', { name: 'Speichern' }).click();
  await expect(page.getByText('Auf diesem Gerät gespeichert')).toBeVisible();

  await context.setOffline(false);
  await expect(page.getByText('Ein Entwurf wurde gesendet')).toBeVisible();
  await expect.poll(async () => {
    const fuel = (await (await request.get(`/api/v1/groups/${group.id}/fuel`)).json()) as { receipts: Receipt[] }[];
    return fuel.map((entry) => entry.receipts.length);
  }).toEqual([1]);
});

test('the group page offers all photos as a ZIP', async ({ page, request }) => {
  const { group } = await createGroupWithCar(request);
  await page.goto(`/g/${group.id}/group`);
  const link = page.getByRole('link', { name: 'Belegfotos als ZIP' });
  await expect(link).toHaveAttribute('href', `/api/v1/groups/${group.id}/receipts.zip`);
  const response = await request.get(`/api/v1/groups/${group.id}/receipts.zip`);
  expect(response.headers()['content-type']).toBe('application/zip');
});

test('an entry with photos stays accessible and fits a narrow phone', async ({ page, request }) => {
  const { group } = await createGroupWithCar(request);
  await page.goto(`/g/${group.id}/fuel/new`);
  await page.getByLabel(/Betrag/).fill('30,00');
  await page.getByTestId('receipt-library').setInputFiles([await photo(page), await photo(page, 400, 300)]);
  await page.getByRole('button', { name: 'Speichern' }).click();
  await expect(page.getByText('Gespeichert', { exact: true })).toBeVisible();
  const fuel = (await (await request.get(`/api/v1/groups/${group.id}/fuel`)).json()) as { id: number }[];

  await page.setViewportSize({ width: 320, height: 640 });
  for (const scheme of ['light', 'dark'] as const) {
    await page.emulateMedia({ colorScheme: scheme });
    await page.goto(`/g/${group.id}/fuel/${fuel[0].id}`);
    await expect(page.getByRole('button', { name: 'Beleg 2 ansehen' })).toBeVisible();
    await page.waitForLoadState('networkidle');
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(0);
    const tags = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'];
    expect((await new AxeBuilder({ page }).withTags(tags).analyze()).violations.map((v) => v.id)).toEqual([]);
    await page.getByRole('button', { name: 'Beleg 2 ansehen' }).click();
    await expect(page.getByRole('dialog', { name: 'Beleg 2' })).toBeVisible();
    expect((await new AxeBuilder({ page }).withTags(tags).analyze()).violations.map((v) => v.id)).toEqual([]);
  }
});
