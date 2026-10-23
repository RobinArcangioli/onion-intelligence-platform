import test from 'node:test';
import assert from 'node:assert/strict';
import { NOTE, APPROVAL, query, compactId, pct, localDateInput } from '../src/lib/util.ts';
import { safePath } from '../src/lib/api.ts';

test('notes respect the API minimum length', () => {
  assert.ok(NOTE.length >= 10);
  assert.ok(APPROVAL.length >= 10);
});
test('query encodes filters rather than concatenating unescaped values', () => {
  assert.equal(query({q: 'a&b', limit: 20, active: false}), '?q=a%26b&limit=20&active=false');
  assert.equal(query({q: '',status: undefined}), '');
});
test('compact identifier never includes a full long onion URL', () => {
  const id = 'a'.repeat(56) + '.onion';
  assert.ok(compactId(id).length < id.length);
});
test('relevance percentage is clamped', () => {
  assert.equal(pct(-9), 0);
  assert.equal(pct(109), 100);
});
test('API client rejects cross-origin and unsafe prefixes', () => {
  assert.equal(safePath('/api/v1/sources'), '/api/v1/sources');
  for (const unsafe of ['https://example.com', '//evil.tld/api/a', '/outside', '/api/\\evil', '/api/../outside', '/api/%2e%2e/outside', '/api/%2foutside', '/api/v1/x#frag']) {
    assert.throws(() => safePath(unsafe));
  }
});
test('localDateInput yields a valid local datetime field', () => {
  assert.match(localDateInput(new Date('2026-10-23T12:13:14Z')), /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/);
});

test('API requests keep key in a same-origin header and disable cache', async () => {
  const { request } = await import('../src/lib/api.ts');
  const old = globalThis.fetch;
  let called = 0;
  globalThis.fetch = (async (url, options) => {
    called++;
    assert.equal(url, '/api/v1/sources?limit=1');
    assert.equal(options?.cache, 'no-store');
    assert.equal(options?.redirect, 'error');
    assert.equal(options?.credentials, 'omit');
    assert.equal(new Headers(options?.headers).get('X-API-Key'), 'test-secret');
    return new Response('{"total":0,"limit":1,"offset":0,"items":[]}', {status:200,headers:{'Content-Type':'application/json'}});
  }) as typeof fetch;
  try {const result = await request('test-secret','/api/v1/sources?limit=1'); assert.equal((result as {total:number}).total,0);assert.equal(called,1);}
  finally {globalThis.fetch=old;}
});

test('invalid API paths never reach fetch', async () => {
  const { request } = await import('../src/lib/api.ts');
  const original=globalThis.fetch;
  globalThis.fetch=((async ()=>{throw Error('fetch must not be called');}) as unknown) as typeof fetch;
  try { await assert.rejects(()=>request('x','https://example.com/api/anything'),/Invalid API route/); }
  finally {globalThis.fetch=original;}
});

test('failed responses surface an HTTP status without leaking body HTML', async () => {
  const { request,ApiError } = await import('../src/lib/api.ts');
  const original=globalThis.fetch;
  globalThis.fetch=(async()=>new Response('<script>bad</script>',{status:502,headers:{'Content-Type':'text/html'}})) as typeof fetch;
  try {await assert.rejects(()=>request('x','/api/v1/sources'),e=> e instanceof ApiError&&e.status===502&&e.message==='HTTP 502');}
  finally {globalThis.fetch=original;}
});
