import { dateTime } from "./util.ts";

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


export function collectionMessage(code: string, retryAt: string | null = null): string {
  const messages: Record<string, string> = {
    CIRCUIT_OPEN: 'Collecte suspendue après plusieurs échecs consécutifs.',
    SOURCE_COOLDOWN: 'Délai minimal entre deux veilles.',
    FETCH_TIMEOUT: 'Délai maximal de collecte dépassé.',
    TOR_NETWORK_ERROR: 'Connexion Tor échouée.',
    BROWSER_CHECK_REQUIRED: 'Vérification du navigateur requise.',
    HTTP_NOT_OK: 'Le site n’a pas renvoyé une page accessible.',
    WORKER_INTERRUPTED: 'Worker interrompu pendant la collecte.',
    AUTHORIZATION_REVOKED: 'URL retirée ou collecte non autorisée.',
    GLOBAL_QUEUE_FULL: 'La file de veille est pleine.',
    WAITING: 'En attente des autres URL du groupe',
  };
  const message = messages[code] ?? code;
  return retryAt ? `${message} Nouvelle tentative possible à partir du ${dateTime(retryAt)}.` : message;
}
