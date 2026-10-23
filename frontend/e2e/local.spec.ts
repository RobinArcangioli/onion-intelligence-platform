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
  await page.getByRole('navigation', { name: 'Navigation principale' })
    .getByRole('button', { name: 'Sources Onion' }).click();
  await expect(page.getByText('Sources Onion').first()).toBeVisible();
  await page.getByRole('button', { name: 'Déconnecter' }).click();
  await expect(page.getByLabel('CLÉ API')).toBeVisible();
});
