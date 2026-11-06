/** UI-only gate: server independently enforces approval and RBAC. */
export function canCollectNow(source: {
  is_active: boolean; approved_for_collection: boolean; collection_enabled: boolean;
}, jobStatus: string | undefined, busy: boolean, role: string): boolean {
  return (role === 'ADMIN' || role === 'ANALYST') && source.is_active && source.approved_for_collection && source.collection_enabled
    && !busy && jobStatus !== 'WAITING' && jobStatus !== 'PENDING' && jobStatus !== 'RUNNING';
}
export function jobLabel(status?: string): string {
  return (status === 'PENDING' || status === 'WAITING') ? 'En attente…'
    : status === 'RUNNING' ? 'En cours…' : '▶ Collecter';
}
