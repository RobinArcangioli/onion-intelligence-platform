import { test, expect } from '@playwright/test';

// Read-only browser smoke against the existing loopback gateway.
// No screenshots/traces/videos because the UI may display sensitive metadata.
test('guest sees login and cannot authenticate with an invalid token', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: /votre espace CTI/i })).toBeVisible();
  await page.getByLabel('CLÉ API').fill('x'.repeat(40));
  await page.getByRole('button', { name: /Accéder au dashboard/i }).click();
  await expect(page.getByRole('alert')).toContainText('Clé API refusée');
});

test('named operator can navigate read-only pages', async ({ page }) => {
  const token = process.env.OIP_E2E_TOKEN;
  test.skip(!token, 'Set OIP_E2E_TOKEN to a VIEWER/ANALYST test token');
  await page.goto('/');
  await page.getByLabel('CLÉ API').fill(token!);
  await page.getByRole('button', { name: /Accéder au dashboard/i }).click();
  await expect(page.getByRole('navigation', { name: 'Navigation principale' })).toBeVisible();
  // Token is not persisted in local/session storage, even while authenticated.
  const stored = await page.evaluate(() => ({ local: Object.keys(localStorage), session: Object.keys(sessionStorage) }));
  expect(stored).toEqual({ local: [], session: [] });
  await page.getByRole('navigation', { name: 'Navigation principale' })
    .getByRole('button', { name: 'Sources Onion' }).click();
  await expect(page.getByText('Sources Onion').first()).toBeVisible();
  // Regression: logout used to be outside the viewport on a short desktop.
  await page.setViewportSize({ width: 1280, height: 600 });
  const logout = page.getByRole('button', { name: 'Déconnecter' });
  await expect(logout).toBeInViewport();
  await logout.click();
  await expect(page.getByLabel('CLÉ API')).toBeVisible();
  await page.reload();
  await expect(page.getByLabel('CLÉ API')).toBeVisible();
});


test('each visible source exposes a manual collection control without triggering it', async ({ page }) => {
  const token = process.env.OIP_E2E_TOKEN;
  test.skip(!token, 'Requires a named operator token');
  await page.goto('/');
  await page.getByLabel('CLÉ API').fill(token!);
  await page.getByRole('button', { name: /Accéder au dashboard/i }).click();
  await Promise.all([
    page.waitForResponse(r => r.url().includes('/api/v1/sources?') && r.status() === 200),
    page.getByRole('navigation', { name: 'Navigation principale' })
      .getByRole('button', { name: 'Sources Onion' }).click(),
  ]);
  await expect(page.getByRole('heading', { name: 'Sources Onion' })).toBeVisible();
  const collectButtons = page.getByRole('button', { name: /^Collecter maintenant :/ });
  const count = await collectButtons.count();
  test.skip(count === 0, 'Source register empty: no collection button to inspect');
  await expect(collectButtons.first()).toBeVisible();
  // No click: the release suite must never visit a real Onion service.
});
