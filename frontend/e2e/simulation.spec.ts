import { test, expect } from '@playwright/test';
const token='oip_CI_SYNTHETIC_NOT_A_REAL_OPERATOR_CREDENTIAL';

test('two fictional leak watches traverse observations, alerts, admin review and public reading',async({page,request,browser})=>{
 test.setTimeout(60000);
 const errors:string[]=[];page.on('response',r=>{if(r.status()>=500)errors.push(`${r.status()} ${new URL(r.url()).pathname}`);});
 expect((await request.post('/api/v1/demo/simulations/run')).status()).toBe(401);
 expect((await (await request.get('/api/public/v1/reports')).json()).total).toBe(0);
 await page.goto('/');await page.getByLabel('CLÉ API').fill(token);
 await page.getByRole('button',{name:'Accéder au dashboard'}).click();
 const nav=page.getByRole('navigation',{name:'Navigation principale'});
 await nav.getByRole('button',{name:'Rapports',exact:true}).click();
 await page.getByRole('button',{name:'Lancer les deux veilles simulées'}).click();
 await expect(page.getByText('2 observations · 2 alertes de fuite · 2 rapports privés prêts.')).toBeVisible();
 const headers={'X-API-Key':token};
 const observations=(await (await request.get('/api/v1/collection/observations',{headers})).json()).items;
 const alerts=(await (await request.get('/api/v1/alerts',{headers})).json()).items;
 const reports=(await (await request.get('/api/v1/reports',{headers})).json()).items;
 expect(observations).toHaveLength(2);expect(alerts).toHaveLength(2);expect(reports).toHaveLength(2);
 for(const alert of alerts){expect(alert.signal_code).toBe('DATA_LEAK_CLAIM');expect(alert.verification_status).toBe('OBSERVED_CLAIM');expect(observations.some((o:{id:string})=>o.id===alert.observation_id)).toBe(true);}
 for(const report of reports)expect(alerts.some((a:{source_id:string})=>a.source_id===report.source_id)).toBe(true);
 expect((await (await request.get('/api/public/v1/reports')).json()).total).toBe(0);
 // A second click/request does not fabricate another set of detections.
 expect((await request.post('/api/v1/demo/simulations/run',{headers})).status()).toBe(200);
 expect((await (await request.get('/api/v1/alerts',{headers})).json()).total).toBe(2);
 await nav.getByRole('button',{name:'Alertes',exact:true}).click();
 await expect(page.getByText('Fuite de données suspectée',{exact:true})).toHaveCount(2);
 page.once('dialog',dialog=>dialog.accept());
 await page.getByRole('button',{name:'Acquitter',exact:true}).first().click();
 await expect(page.getByRole('button',{name:'Acquitter',exact:true})).toHaveCount(1);
 page.once('dialog',dialog=>dialog.accept());
 await page.getByRole('button',{name:'Acquitter',exact:true}).click();
 await expect(page.getByRole('button',{name:'Acquitter',exact:true})).toHaveCount(0);
 await nav.getByRole('button',{name:'Rapports',exact:true}).click();
 const visitorContext=await browser.newContext({baseURL:new URL(page.url()).origin});
 try{
  const visitor=await visitorContext.newPage();
  visitor.on('request',r=>{if(new URL(r.url()).pathname.startsWith('/api/'))expect(new URL(r.url()).pathname).toMatch(/^\/api\/public\/v1\//);});
  await visitor.goto('/');await visitor.getByRole('button',{name:'Accès visiteur',exact:true}).click();
  await visitor.getByRole('button',{name:'Rapports publics',exact:true}).click();
  await expect(visitor.getByRole('heading',{name:'Aucun rapport public'})).toBeVisible();
  const publicIds:string[]=[];
  for(const code of ['ALPHA-01','BETA-02']){
   const company=`Entreprise fictive ${code}`;
   const row=page.getByRole('row').filter({hasText:company});
   await row.getByRole('button',{name:'Vitrine',exact:true}).click();
   const dialog=page.getByRole('dialog',{name:'Publication publique du rapport'});
   await expect(dialog.getByLabel('Entreprise concernée',{exact:true})).toHaveValue(company);
   await expect(dialog.getByRole('button',{name:'Publier le rapport relu'})).toBeDisabled();
   const summary=dialog.getByRole('textbox',{name:'Synthèse publique',exact:true});
   await summary.fill((await summary.inputValue())+' Synthèse relue pour publication dans cet exercice fictif.');
   await dialog.getByRole('button',{name:'Mettre à jour l’aperçu'}).click();
   await expect(dialog.getByRole('button',{name:'Mettre à jour l’aperçu'})).toHaveCount(0);
   await dialog.getByLabel('J’ai vérifié ces informations et j’autorise leur publication publique.').check();
   const response=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname.endsWith('/publication'));
   await dialog.getByRole('button',{name:'Publier le rapport relu'}).click();
   publicIds.push((await (await response).json()).publication_id);
   await expect(dialog.getByText('Ce rapport possède une version publique.')).toBeVisible();
   await dialog.getByRole('button',{name:'Fermer',exact:true}).click();
   await visitor.bringToFront();
   const card=visitor.locator(`[data-publication-id="${publicIds.at(-1)}"]`);
   await expect(card).toBeVisible({timeout:12000});
   await card.getByRole('button',{name:'Consulter le rapport'}).click();
   const reader=visitor.getByRole('dialog',{name:'Consulter le rapport public'});
   await expect(reader.getByText(company,{exact:true})).toBeVisible();
   await expect(reader.getByText('SIMULATION — entreprise et données entièrement fictives')).toBeVisible();
   await expect(reader).toContainText('Synthèse relue pour publication dans cet exercice fictif.');
   await expect(reader).not.toContainText('SIMULATION_INTERNAL_CONTEXT');
   expect(await reader.innerText()).not.toMatch(/\.onion|observation_id|source_id/);
   await reader.getByRole('button',{name:'Fermer le rapport'}).click();
  }
  expect((await (await request.get('/api/public/v1/reports')).json()).total).toBe(2);
  // Withdrawal revokes the URL, without deleting internal reports or alerts.
  await page.getByRole('row').filter({hasText:'Entreprise fictive ALPHA-01'}).getByRole('button',{name:'Vitrine',exact:true}).click();
  const dialog=page.getByRole('dialog',{name:'Publication publique du rapport'});
  await expect(dialog.getByText('Synthèse relue pour publication dans cet exercice fictif.',{exact:false}).last()).toBeVisible();
  await dialog.getByRole('button',{name:'Retirer de la vitrine'}).click();
  await expect(dialog.getByText('Ce rapport n’est pas publié.')).toBeVisible();
  expect((await request.get('/api/public/v1/reports/'+publicIds[0])).status()).toBe(404);
  expect((await (await request.get('/api/v1/reports',{headers})).json()).total).toBe(2);
  expect(errors).toEqual([]);
 }finally{await visitorContext.close();}
});
