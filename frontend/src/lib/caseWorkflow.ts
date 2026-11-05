/** UI affordances only; the API independently enforces every transition. */
import type { CaseAction, CaseStatus } from './types';
export function canCaseTransition(status: CaseStatus, action: CaseAction): boolean {
  if (status === 'CLOSED') return false;
  if (action === 'ASSIGN' || action === 'UNASSIGN' || action === 'SET_PRIORITY') return true;
  if (action === 'START_REVIEW') return status === 'OPEN';
  if (action === 'ESCALATE') return status === 'IN_REVIEW';
  if (action === 'RETURN_REVIEW') return status === 'ESCALATED';
  return action === 'CLOSE' && (status === 'IN_REVIEW' || status === 'ESCALATED');
}
