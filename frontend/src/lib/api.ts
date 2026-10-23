/** Same-origin API only. API key exists only in React memory, not localStorage or a cookie. */
export class ApiError extends Error {
  public status: number;
  constructor(status: number, message: string) { super(message); this.name = 'ApiError'; this.status = status; }
}
export function safePath(path: string): string {
  // Reject dot-segment normalization and URL encoding tricks before attaching a secret.
  // The browser must never normalize an API route to a static or outside-origin path.
  if (!path.startsWith('/api/') || path.startsWith('//') || path.includes('\\')
      || /[\r\n\t#]/.test(path) || /%(?:2e|2f|5c|00)/i.test(path)) {
    throw new Error('Invalid API route');
  }
  const parsed = new URL(path, 'http://oip.invalid');
  if (parsed.origin !== 'http://oip.invalid' || !parsed.pathname.startsWith('/api/')) {
    throw new Error('Invalid API route');
  }
  return path;
}
export async function request<T>(key: string, path: string, init: RequestInit = {}): Promise<T> {
  const url = safePath(path);
  const headers = new Headers(init.headers);
  headers.set('X-API-Key', key);
  if (init.body !== undefined) headers.set('Content-Type', 'application/json');
  const response = await fetch(url, {
    ...init, headers, cache: 'no-store', credentials: 'omit', redirect: 'error',
  });
  if (!response.ok) {
    let detail: string | undefined;
    try {
      const payload: unknown = await response.json();
      if (typeof payload === 'object' && payload !== null && 'detail' in payload) {
        const message = (payload as { detail: unknown }).detail;
        detail = typeof message === 'string' ? message : undefined;
      }
    } catch { /* Invalid/error HTML response: do not expose it in the UI. */ }
    throw new ApiError(response.status, detail || `HTTP ${response.status}`);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
export const api = {
  get: <T>(key: string, path: string) => request<T>(key, path),
  post: <T>(key: string, path: string, body: unknown) => request<T>(key, path, { method: 'POST', body: JSON.stringify(body) }),
  patch: <T>(key: string, path: string, body: unknown) => request<T>(key, path, { method: 'PATCH', body: JSON.stringify(body) }),
};
export async function downloadExport(key: string, path: string, filename: string): Promise<void> {
  const response = await fetch(safePath(path), {
    headers: { 'X-API-Key': key }, cache: 'no-store', credentials: 'omit', redirect: 'error',
  });
  if (!response.ok) throw new ApiError(response.status, `Export impossible (HTTP ${response.status})`);
  const blob = await response.blob();
  const link = document.createElement('a');
  const url = URL.createObjectURL(blob);
  try {
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
  } finally {
    link.remove();
    URL.revokeObjectURL(url);
  }
}
