import assert from 'node:assert/strict';
import { test } from 'node:test';
import { publicGet } from '../src/lib/publicApi.ts';

test('anonymous public requests never attach credentials or operator headers',async()=>{
 const original=globalThis.fetch;let call:RequestInit|undefined;
 try{
  globalThis.fetch=async(_url,init)=>{call=init;return new Response(JSON.stringify({items:[],total:0}),{status:200,headers:{'content-type':'application/json'}});};
  await publicGet('/api/public/v1/activity?limit=20');
  assert.equal(call?.method,'GET');assert.equal(call?.credentials,'omit');assert.equal(call?.cache,'no-store');assert.equal(call?.redirect,'error');
  assert.equal(call?.headers,undefined);
 }finally{globalThis.fetch=original;}
});

test('public client rejects internal or external endpoints before fetching',async()=>{
 for(const path of ['/api/v1/sources','https://external.invalid/api/public/v1/activity','/api/public/v1/../v1/sources','/api/public/v1/activity/11111111-1111-4111-8111-111111111111']){
  await assert.rejects(()=>publicGet(path));
 }
});

test('anonymous error messages do not reflect private server response bodies',async()=>{
 const original=globalThis.fetch;
 try{
  globalThis.fetch=async()=>new Response('INTERNAL_PRIVATE_SENTINEL',{status:503});
  await assert.rejects(()=>publicGet('/api/public/v1/reports'),error=>error instanceof Error&&!error.message.includes('INTERNAL_PRIVATE_SENTINEL'));
 }finally{globalThis.fetch=original;}
});
