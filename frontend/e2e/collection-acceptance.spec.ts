import { expect, test } from '@playwright/test';

const token = 'oip_CI_SYNTHETIC_NOT_A_REAL_OPERATOR_CREDENTIAL';
const headers = { 'X-API-Key': token };
const fixturePath = '/api/v1/demo/acceptance';
const activeMarkup = '<img src="/fixture-must-not-load" onerror="window.__oipInjected=1">';
const marketplace = 'Marché synthétique Atlas';

test('a group collection and an operator capture lead to a safe visitor report', async ({ page, request, browser }) => {
  test.setTimeout(65_000);
  const requests: string[] = [];
  page.on('request', event => requests.push(event.url()));

  expect((await request.get(fixturePath)).status()).toBe(401);
  const fixtureResponse = await request.get(fixturePath, { headers });
  expect(fixtureResponse.status()).toBe(200);
  const { root, discovered } = await fixtureResponse.json();
  const catalogue = root + 'catalogue';
  const notes = root + 'notes';
  const captured = root + 'capture';
  const sourceOnly = root + 'manual';

  await page.goto('/');
  await page.getByLabel('CLÉ API').fill('x'.repeat(40));
  await page.getByRole('button', { name: 'Accéder au dashboard' }).click();
  await expect(page.getByRole('alert')).toContainText('Clé API refusée');
  await page.getByLabel('CLÉ API').fill(token);
  await page.getByRole('button', { name: 'Accéder au dashboard' }).click();
  const nav = page.getByRole('navigation', { name: 'Navigation principale' });
  await expect(nav).toBeVisible();
  expect(await page.evaluate(() => [Object.keys(localStorage), Object.keys(sessionStorage)])).toEqual([[], []]);

  await nav.getByRole('button', { name: 'Watchlists', exact: true }).click();
  await page.getByLabel('Nouvelle watchlist').fill('Règles de recette');
  await page.getByRole('button', { name: 'Créer', exact: true }).click();
  await page.getByRole('button', { name: /Règles de recette/ }).click();
  for (const phrase of ['atlasneedle', 'nav-only-trigger', 'script-only-trigger']) {
    await page.getByLabel('Nouvelle expression').fill(phrase);
    await page.getByRole('button', { name: 'Ajouter', exact: true }).click();
    await expect(page.getByText(phrase, { exact: true })).toBeVisible();
  }

  await nav.getByRole('button', { name: 'Sources Onion', exact: true }).click();
  await page.getByRole('button', { name: 'Ajouter une source' }).click();
  const newSource = page.getByRole('dialog', { name: 'Ajouter une source' });
  await newSource.getByLabel('Nom (visible dans la vitrine)').fill(marketplace);
  await newSource.getByLabel('Première URL Onion du groupe').fill(root);
  await newSource.getByRole('checkbox').check();
  await newSource.getByRole('button', { name: 'Enregistrer', exact: true }).click();
  const row = page.getByRole('row').filter({ hasText: marketplace });
  const collect = row.getByRole('button', { name: `Collecter maintenant : ${marketplace}` });
  await expect(collect).toBeDisabled();
  await row.getByRole('button', { name: 'Gérer les URL' }).click();
  const pages = page.getByRole('dialog', { name: `URL de ${marketplace}` });
  const urlField = pages.getByLabel('URL Onion finale');
  const add = pages.getByRole('button', { name: 'Ajouter l’URL', exact: true });
  for (const url of [catalogue, notes]) {
    await urlField.fill(url);
    await add.click();
    await expect(pages.getByText(url, { exact: true })).toBeVisible();
  }
  const sources = await (await request.get('/api/v1/sources', { headers })).json();
  expect(sources.items).toHaveLength(1);
  const sourceId = sources.items[0].id;
  const sourcePath = `/api/v1/sources/${sourceId}`;
  expect((await (await request.get('/api/v1/collection/jobs', { headers })).json()).total).toBe(0);
  await pages.getByRole('button', { name: 'Fermer', exact: true }).click();
  page.once('dialog', dialog => dialog.accept());
  await row.getByRole('button', { name: 'Autoriser collecte' }).click();
  await expect(collect).toBeEnabled();
  await collect.click();
  await row.getByRole('button', { name: 'Gérer les URL' }).click();
  const progress = pages.getByRole('region', { name: 'Progression de la veille' });
  await expect(progress).toContainText('URL en cours');
  await expect(progress).toContainText(root);
  expect((await request.post(fixturePath + '/release', { headers })).status()).toBe(200);
  await expect(progress).toContainText('3 / 3 URL traitées');
  await expect(pages.getByText('Vérification du navigateur requise.')).toBeVisible();
  const visited = (await (await request.get(fixturePath, { headers })).json()).visited;
  expect(visited[0]).toBe(root);
  expect([...visited].sort()).toEqual([root, catalogue, notes].sort());

  await urlField.fill(sourceOnly);
  await add.click();
  await expect(pages.getByText(sourceOnly, { exact: true })).toBeVisible();
  await urlField.fill(captured);
  await pages.getByLabel('Texte visible dans Tor Browser').fill('atlasneedle texte capturé ' + activeMarkup);
  await pages.getByRole('button', { name: 'Ajouter et analyser maintenant' }).click();
  await expect(pages.getByText(/Analyse terminée. 1 occurrence/)).toBeVisible();
  await expect(pages.getByText(captured, { exact: true })).toBeVisible();
  expect((await (await request.get(fixturePath, { headers })).json()).visited).toEqual(visited);
  const observations = (await (await request.get('/api/v1/collection/observations', { headers })).json()).items;
  expect(observations).toHaveLength(3);
  expect(observations.find(item => item.origin === 'OPERATOR_CAPTURE').http_status).toBeNull();
  const alerts = (await (await request.get('/api/v1/alerts', { headers })).json()).items;
  expect(alerts.map(item => item.event_type)).toEqual(['WATCHLIST_MATCH', 'WATCHLIST_MATCH']);
  const discoveries = (await (await request.get('/api/v1/collection/discoveries', { headers })).json()).items;
  expect(discoveries.map(item => item.target_url)).toEqual([discovered]);

  await pages.getByRole('button', { name: 'Fermer', exact: true }).click();
  await nav.getByRole('button', { name: 'Observations', exact: true }).click();
  await expect(page.getByText(activeMarkup, { exact: true })).toBeVisible();
  await expect(page.locator('img[src="/fixture-must-not-load"], iframe[src="/fixture-must-not-load"]')).toHaveCount(0);
  expect(await page.evaluate(() => Reflect.has(window, '__oipInjected'))).toBe(false);

  await nav.getByRole('button', { name: 'Rapports', exact: true }).click();
  await page.getByRole('button', { name: 'Générer un rapport' }).click();
  const reportForm = page.getByRole('dialog', { name: 'Créer un rapport' });
  await reportForm.getByLabel('Date de fin').fill(new Date(Date.now() + 120_000).toISOString().slice(0, 16));
  await reportForm.getByRole('combobox').selectOption(sourceId);
  await reportForm.getByRole('button', { name: 'Créer le rapport' }).click();
  await expect(page.getByText('Rapport créé.')).toBeVisible();
  expect((await (await request.get('/api/public/v1/reports')).json()).total).toBe(0);
  await page.getByRole('button', { name: 'Vitrine', exact: true }).click();
  const publication = page.getByRole('dialog', { name: 'Publication publique du rapport' });
  await publication.getByRole('button', { name: 'Publier ces compteurs' }).click();
  await expect(publication.getByText('Ce rapport possède une version publique.')).toBeVisible();
  const publicReport = (await (await request.get('/api/public/v1/reports')).json()).items[0];
  expect(publicReport.content.totals).toMatchObject({ observations: 3, alerts: 2, discoveries: 1 });

  const visitor = await browser.newContext({ baseURL: new URL(page.url()).origin });
  try {
    const guest = await visitor.newPage();
    guest.on('request', event => requests.push(event.url()));
    await guest.goto('/');
    await guest.getByRole('button', { name: 'Accès visiteur' }).click();
    await guest.getByRole('button', { name: 'Rapports publics' }).click();
    await guest.getByRole('button', { name: 'Consulter le rapport' }).click();
    const reader = guest.getByRole('dialog', { name: 'Consulter le rapport public' });
    await expect(reader).toBeVisible();
    expect(await reader.innerText()).not.toMatch(/\.onion|__oipInjected|atlasneedle/);
    for (const route of [sourcePath + '/collection/run', sourcePath + '/pages/capture']) {
      expect((await visitor.request.post(route, { data: {} })).status()).toBe(401);
    }
    await publication.getByRole('button', { name: 'Retirer de la vitrine' }).click();
    await expect(publication.getByText('Ce rapport n’est pas publié.')).toBeVisible();
    await guest.bringToFront();
    await expect(reader.getByRole('alert')).toContainText('Ce rapport n’est plus public.', { timeout: 12000 });
    await expect(reader.locator('dl')).toHaveCount(0);
    expect((await visitor.request.get('/api/public/v1/reports/' + publicReport.id)).status()).toBe(404);
  } finally {
    await visitor.close();
  }

  await publication.getByRole('button', { name: 'Fermer', exact: true }).click();
  await nav.getByRole('button', { name: 'Sources Onion', exact: true }).click();
  expect((await request.put(fixturePath + '/emergency-stop', { headers, data: { enabled: true } })).status()).toBe(200);
  await collect.click();
  await expect(page.getByText(/Arrêt d'urgence de la collecte activé/)).toBeVisible();
  await request.put(fixturePath + '/emergency-stop', { headers, data: { enabled: false } });
  await row.getByRole('button', { name: 'Pause', exact: true }).click();
  await expect(collect).toBeDisabled();
  expect((await request.post(sourcePath + '/collection/run', { headers, data: { reason: 'Synthetic check' } })).status()).toBe(409);
  expect(requests.every(url => url.startsWith('http://127.0.0.1:8000/') && !url.includes('fixture-must-not-load'))).toBe(true);
});
