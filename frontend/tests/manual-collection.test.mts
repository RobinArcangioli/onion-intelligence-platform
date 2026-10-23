import test from 'node:test';
import assert from 'node:assert/strict';
import { canCollectNow, jobLabel } from '../src/lib/manualCollection.ts';
test('manual collect disabled for unapproved, inactive, unauthorized and active jobs',()=>{
 const base={is_active:true,approved_for_collection:true,collection_enabled:true};
 assert.equal(canCollectNow(base,undefined,false,'ANALYST'),true);
 for(const name of ['is_active','approved_for_collection','collection_enabled'] as const)
   assert.equal(canCollectNow({...base,[name]:false},undefined,false,'ANALYST'),false);
 for(const status of ['PENDING','RUNNING']) assert.equal(canCollectNow(base,status,false,'ANALYST'),false);
 assert.equal(canCollectNow(base,'FAILED',false,'ADMIN'),true);
 assert.equal(canCollectNow(base,'FAILED',false,'VIEWER'),false);
 assert.equal(canCollectNow(base,'COMPLETED',true,'ADMIN'),false);
});
test('labels identify pending and running jobs',()=>{
 assert.equal(jobLabel('PENDING'),'En attente…');
 assert.equal(jobLabel('RUNNING'),'En cours…');
 assert.equal(jobLabel('COMPLETED'),'▶ Collecter');
});
