import { test, expect } from '@playwright/test';
const fixtureToken='oip_CI_SYNTHETIC_NOT_A_REAL_OPERATOR_CREDENTIAL';

test('visitor browses metadata and published reports without internal requests or credentials',async({page})=>{
 const requests:{path:string;key:string|undefined}[]=[];
 page.on('request',r=>{if(new URL(r.url()).pathname.startsWith('/api/'))requests.push({path:new URL(r.url()).pathname,key:r.headers()['x-api-key']});});
 await page.goto('/');
 await page.getByRole('button',{name:'Accès visiteur',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Dernières veilles',exact:true})).toBeVisible();
 await expect(page.getByRole('cell',{name:'Source de démonstration'})).toBeVisible();
 await expect(page.getByText('12 500',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Rapports publics',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Rapport de veille',exact:true})).toHaveCount(1);
 expect(await page.locator('body').innerText()).not.toMatch(/\.onion|INTERNAL_PRIVATE_SENTINEL|11111111-1111/);
 expect(requests.length).toBeGreaterThan(0);
 expect(requests.every(r=>r.path.startsWith('/api/public/v1/')&&!r.key)).toBe(true);
 await page.getByRole('button',{name:'Connexion opérateur',exact:true}).last().click();
 await expect(page.getByLabel('CLÉ API')).toBeVisible();
 expect(await page.evaluate(()=>[Object.keys(localStorage),Object.keys(sessionStorage)])).toEqual([[],[]]);
});

test('admin keeps token login and can preview, publish and withdraw a private report',async({page,request})=>{
 const failures:string[]=[];page.on('pageerror',e=>failures.push(e.message));
 page.on('response',r=>{if(r.status()>=500)failures.push(`${r.status()} ${new URL(r.url()).pathname}`);});
 await page.goto('/');await page.getByLabel('CLÉ API').fill(fixtureToken);
 await page.getByRole('button',{name:'Accéder au dashboard'}).click();
 await page.getByRole('navigation',{name:'Navigation principale'}).getByRole('button',{name:'Rapports',exact:true}).click();
 const buttons=page.getByRole('button',{name:'Vitrine',exact:true});
 await expect(buttons).toHaveCount(2);
 for(let index=0;index<2;index++){
  await buttons.nth(index).click();
  const dialog=page.getByRole('dialog',{name:'Publication publique du rapport'});
  await expect(dialog.getByRole('status')).toContainText(/Ce rapport/);
  if(await dialog.getByRole('button',{name:'Publier ces compteurs'}).count())break;
  await dialog.getByRole('button',{name:'Fermer',exact:true}).click();
 }
 const dialog=page.getByRole('dialog',{name:'Publication publique du rapport'});
 await expect(dialog).not.toContainText('INTERNAL_PRIVATE_SENTINEL');
 await dialog.getByRole('button',{name:'Publier ces compteurs'}).click();
 await expect(dialog.getByText('Ce rapport possède une version publique.')).toBeVisible();
 expect((await (await request.get('/api/public/v1/reports')).json()).total).toBe(2);
 await dialog.getByRole('button',{name:'Retirer de la vitrine'}).click();
 await expect(dialog.getByText('Ce rapport n’est pas publié.')).toBeVisible();
 expect((await (await request.get('/api/public/v1/reports')).json()).total).toBe(1);
 expect((await request.get('/api/v1/reports')).status()).toBe(401);
 await dialog.getByRole('button',{name:'Fermer',exact:true}).click();
 await page.getByRole('button',{name:'Déconnecter'}).click();
 await expect(page.getByLabel('CLÉ API')).toHaveValue('');
 expect(failures).toEqual([]);
});

test('visitor handles unavailable and empty public data without reflecting error details',async({page})=>{
 await page.route('**/api/public/v1/activity?*',route=>route.fulfill({status:503,body:'INTERNAL_PRIVATE_SENTINEL'}));
 await page.route('**/api/public/v1/reports?*',route=>route.fulfill({json:{items:[],total:0,limit:20,offset:0}}));
 await page.goto('/');await page.getByRole('button',{name:'Accès visiteur',exact:true}).click();
 await expect(page.getByRole('alert')).toContainText('temporairement indisponible');
 await expect(page.locator('body')).not.toContainText('INTERNAL_PRIVATE_SENTINEL');
 await page.getByRole('button',{name:'Rapports publics',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Aucun rapport public'})).toBeVisible();
 await page.setViewportSize({width:390,height:844});
 await expect(page.getByRole('button',{name:'Dernières veilles',exact:true})).toBeInViewport();
 await expect(page.getByRole('button',{name:'Connexion opérateur',exact:true}).last()).toBeInViewport();
});
