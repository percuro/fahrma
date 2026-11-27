import { expect, test, type Page } from '@playwright/test';
import { anonymousPage, axeViolations, createGroupWithCar, today } from './helpers';

// design.spec.ts scans every page of a group as it loads; this covers what appears after a click,
// the administration, the pages without an account, the English interface and the change of page.

async function heading(page: Page) {
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await page.waitForLoadState('networkidle');
}

for (const scheme of ['light', 'dark'] as const) {
  test(`administration, forms and dialogs without violations in the ${scheme} scheme`, async ({ page, request }) => {
    await page.emulateMedia({ colorScheme: scheme, reducedMotion: 'reduce' });
    const found: string[] = [];
    const { group, car, me } = await createGroupWithCar(request);
    const day = await today(request);
    const base = `/api/v1/groups/${group.id}`;
    expect(
      (await request.post(`${base}/trips`, {
        data: { car_id: car.id, date: day, start_km: 10000, end_km: 10050, shares: [{ user_id: me, weight: 1 }] },
      })).status(),
    ).toBe(201);

    // Every tab of the instance administration
    await page.goto('/admin');
    await heading(page);
    for (const tab of ['Zugänge', 'Gruppen', 'Einladungen', 'Sicherheit']) {
      await page.getByRole('tab', { name: tab }).click();
      await expect(page.getByRole('tab', { name: tab })).toHaveAttribute('aria-selected', 'true');
      await page.waitForLoadState('networkidle');
      found.push(...(await axeViolations(page, `/admin ${tab}`)));
    }

    // Forms not scanned by design.spec.ts, and a form showing an error
    for (const path of [`/g/${group.id}/expense/new`, `/g/${group.id}/reservation/new`, '/import']) {
      await page.goto(path);
      await heading(page);
      found.push(...(await axeViolations(page, path)));
    }
    await page.goto(`/g/${group.id}/expense/new`);
    await heading(page);
    await page.getByRole('button', { name: 'Speichern' }).click();
    found.push(...(await axeViolations(page, 'expense form with an error')));

    // The confirmation dialog, e.g. before settling
    await page.goto(`/g/${group.id}/settlement`);
    await heading(page);
    await page.getByRole('button', { name: 'Jetzt abrechnen' }).click();
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();
    found.push(...(await axeViolations(page, 'confirmation dialog')));
    await dialog.getByRole('button', { name: 'Abbrechen' }).click();
    await expect(dialog).toBeHidden();

    // The own security log on the profile
    await page.goto('/profile');
    await heading(page);
    await expect(page.getByRole('heading', { name: 'Letzte Sicherheitsereignisse' })).toBeVisible();
    found.push(...(await axeViolations(page, '/profile with the security log')));
    expect(found).toEqual([]);
  });

  test(`pages without an account without violations in the ${scheme} scheme`, async ({ browser }) => {
    const { context, page } = await anonymousPage(browser);
    await page.emulateMedia({ colorScheme: scheme, reducedMotion: 'reduce' });
    const found: string[] = [];
    for (const path of ['/register', '/forgot-password', '/invite']) {
      await page.goto(path);
      await heading(page);
      found.push(...(await axeViolations(page, path)));
    }
    await context.close();
    expect(found).toEqual([]);
  });
}

test('the administration and the pages without an account fit 320 px', async ({ page, browser }) => {
  await page.setViewportSize({ width: 320, height: 640 });
  const overflow = (target: Page) =>
    target.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  await page.goto('/admin');
  await heading(page);
  for (const tab of ['Zugänge', 'Gruppen', 'Einladungen', 'Sicherheit']) {
    await page.getByRole('tab', { name: tab }).click();
    await page.waitForLoadState('networkidle');
    expect(await overflow(page), tab).toBeLessThanOrEqual(0);
  }
  const { context, page: anonymous } = await anonymousPage(browser);
  await anonymous.setViewportSize({ width: 320, height: 640 });
  for (const path of ['/register', '/forgot-password', '/invite']) {
    await anonymous.goto(path);
    await heading(anonymous);
    expect(await overflow(anonymous), path).toBeLessThanOrEqual(0);
  }
  await context.close();
});

test('the English interface without violations', async ({ page, request }) => {
  const { group } = await createGroupWithCar(request);
  expect((await request.patch('/api/v1/auth/me', { data: { locale: 'en' } })).status()).toBe(200);
  try {
    const found: string[] = [];
    for (const path of [`/g/${group.id}`, `/g/${group.id}/trip/new`, `/g/${group.id}/settlement`, '/profile', '/admin']) {
      await page.goto(path);
      await heading(page);
      await expect(page.locator('html')).toHaveAttribute('lang', 'en');
      found.push(...(await axeViolations(page, `en ${path}`)));
    }
    expect(found).toEqual([]);
  } finally {
    await request.patch('/api/v1/auth/me', { data: { locale: null } });
  }
});

test('after a change of page the focus is at the content and the page is announced', async ({ page, request }) => {
  const { group } = await createGroupWithCar(request);
  await page.goto(`/g/${group.id}`);
  await heading(page);
  // Not on the first load: the browser announces the page itself
  await expect(page.locator('#page-announcer')).toHaveText('');

  await page.getByRole('navigation', { name: 'Bereiche' }).getByRole('link', { name: 'Verlauf' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Verlauf' })).toBeVisible();
  await expect(page.locator('main#content')).toBeFocused();
  await expect(page.locator('#page-announcer')).toHaveText('Verlauf');
  // The next Tab goes to the first control of the page, not back to the navigation
  await page.keyboard.press('Tab');
  expect(await page.evaluate(() => document.getElementById('content')?.contains(document.activeElement))).toBe(true);

  // A page loaded on first use (its own chunk) is announced too
  await page.goto('/profile');
  await heading(page);
  await page.getByRole('link', { name: 'Verwaltung der Instanz' }).click();
  await expect(page.locator('#page-announcer')).toHaveText('Verwaltung der Instanz');
  await expect(page.locator('main#content')).toBeFocused();
});
