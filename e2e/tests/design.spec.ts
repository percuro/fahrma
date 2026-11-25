import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';
import { anonymousPage, createGroupWithCar, today } from './helpers';

/** The pages of a group with a running trip, a finished trip and a fuel entry. */
async function pagesOf(page: Page) {
  const request = page.request;
  const { group, car, me } = await createGroupWithCar(request);
  const day = await today(request);
  const base = `/api/v1/groups/${group.id}`;
  const shares = [{ user_id: me, weight: 1 }];
  expect((await request.post(`${base}/trips`, { data: { car_id: car.id, date: day, start_km: 10000, end_km: 10100, shares } })).status()).toBe(201);
  expect(
    (
      await request.post(`${base}/fuel`, {
        data: { car_id: car.id, date: day, odometer_km: 10100, quantity_milli: 40000, amount_cents: 6400, paid_by_user_id: me, full_tank: true },
      })
    ).status(),
  ).toBe(201);
  expect((await request.post(`${base}/trips`, { data: { car_id: car.id, date: day, start_km: 10100, end_km: null, shares } })).status()).toBe(201);
  const g = `/g/${group.id}`;
  return [g, `${g}/trip/new`, `${g}/fuel/new`, `${g}/calendar`, `${g}/history`, `${g}/settlement`, `${g}/group`, `${g}/stats`, '/profile'];
}

async function open(page: Page, path: string) {
  await page.goto(path);
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await page.waitForLoadState('networkidle');
}

for (const scheme of ['light', 'dark'] as const) {
  test(`no accessibility violations in the ${scheme} scheme (WCAG 2.2 AA)`, async ({ page, browser }) => {
    await page.emulateMedia({ colorScheme: scheme });
    const found: string[] = [];
    const scan = async (target: Page, path: string) => {
      await open(target, path);
      const result = await new AxeBuilder({ page: target }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']).analyze();
      found.push(...result.violations.map((v) => `${path}: ${v.id} (${v.nodes.length}) ${v.nodes[0].target.join(' ')}`));
    };
    for (const path of await pagesOf(page)) await scan(page, path);

    const anonymous = await anonymousPage(browser);
    await anonymous.page.emulateMedia({ colorScheme: scheme });
    await scan(anonymous.page, '/');
    await anonymous.context.close();
    expect(found).toEqual([]);
  });
}

test('every page fits a window 320 px wide without scrolling sideways', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 640 });
  for (const path of await pagesOf(page)) {
    await open(page, path);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, path).toBeLessThanOrEqual(0);
  }
});

test('the window title follows the page, the navigation follows the width', async ({ page }) => {
  const [overview, trip] = await pagesOf(page);
  await open(page, trip);
  await expect(page).toHaveTitle('Neue Fahrt · fahrma');

  const navigation = page.getByRole('navigation', { name: 'Bereiche' });
  const position = () => navigation.evaluate((element) => getComputedStyle(element).position);
  // Phone and tablet: at the bottom, within reach of the thumb; wide window: in the top bar
  await page.setViewportSize({ width: 390, height: 800 });
  await open(page, overview);
  expect(await position()).toBe('fixed');
  await expect(navigation.getByRole('link', { name: 'Übersicht' })).toHaveAttribute('aria-current', 'page');
  await page.setViewportSize({ width: 1000, height: 800 });
  expect(await position()).toBe('static');
});
