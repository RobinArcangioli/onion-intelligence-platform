import test from 'node:test';
import assert from 'node:assert/strict';
import { canCaseTransition } from '../src/lib/caseWorkflow.ts';
import type { CaseStatus, CaseAction } from '../src/lib/types.ts';

test('no case mutation can be offered after closure', () => {
  const actions: CaseAction[]=['ASSIGN','UNASSIGN','START_REVIEW','ESCALATE','RETURN_REVIEW','CLOSE','SET_PRIORITY'];
  for (const action of actions) assert.equal(canCaseTransition('CLOSED',action),false);
});
test('workflow UI exposes only legal status transitions', () => {
  const statuses: CaseStatus[]=['OPEN','IN_REVIEW','ESCALATED'];
  const permitted: Record<CaseStatus,CaseAction[]> = {
    OPEN:['ASSIGN','UNASSIGN','START_REVIEW','SET_PRIORITY'],
    IN_REVIEW:['ASSIGN','UNASSIGN','ESCALATE','CLOSE','SET_PRIORITY'],
    ESCALATED:['ASSIGN','UNASSIGN','RETURN_REVIEW','CLOSE','SET_PRIORITY'],
    CLOSED:[],
  };
  const actions: CaseAction[]=['ASSIGN','UNASSIGN','START_REVIEW','ESCALATE','RETURN_REVIEW','CLOSE','SET_PRIORITY'];
  for (const status of statuses) for (const action of actions)
    assert.equal(canCaseTransition(status,action),permitted[status].includes(action),`${status}:${action}`);
});

test('priority changes are allowed only before case closure', () => {
  for (const state of ['OPEN','IN_REVIEW','ESCALATED'] as const)
    assert.equal(canCaseTransition(state,'SET_PRIORITY'),true);
  assert.equal(canCaseTransition('CLOSED','SET_PRIORITY'),false);
});
