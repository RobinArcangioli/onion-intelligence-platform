/** No third-party formats, no user-provided links and no HTML injection. */
export const NOTE = 'Manual check';
export const APPROVAL = 'Manual approval';
export const limit = 20;
export function query(params: Record<string, string | number | boolean | undefined | null>): string {
  const p = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') p.set(key, String(value));
  }
  return p.toString() ? `?${p.toString()}` : '';
}
export function compactId(value: string | null | undefined, front = 9): string {
  if (!value) return '—';
  return value.length > front + 7 ? `${value.slice(0, front)}…${value.slice(-6)}` : value;
}
export function dateTime(value: string | null | undefined): string {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return '—';
  return new Intl.DateTimeFormat('fr-FR', { dateStyle: 'medium', timeStyle: 'short' }).format(d);
}
export function shortNumber(value: number): string { return new Intl.NumberFormat('fr-FR').format(value); }
export function pct(value: number): number { return Math.max(0, Math.min(100, value)); }
export function localDateInput(date: Date): string {
  const shifted = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return shifted.toISOString().slice(0, 16);
}
export function priorDays(days: number): Date { return new Date(Date.now() - days * 86400000); }
export function readableError(error: unknown): string { return error instanceof Error ? error.message : 'Erreur inconnue'; }
