import { useEffect, useState } from 'react';
import { api } from '../lib/api';

type Credential = {
  id: string; label: string; created_at: string | null;
  expires_at: string; status: 'ACTIVE' | 'EXPIRED' | 'REVOKED'; current: boolean;
};
type Inventory = { items: Credential[]; total: number; limit: number; offset: number };

export function AccessInventory({ token, refresh }: { token: string; refresh: number }) {
  const [page, setPage] = useState(0);
  const [data, setData] = useState<Inventory | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api.get<Inventory>(token, `/api/v1/auth/tokens?limit=20&offset=${page * 20}`)
      .then(result => { if (!cancelled) { setData(result); setError(''); } })
      .catch(() => { if (!cancelled) { setData(null); setError('Inventaire indisponible.'); } })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [token, page, refresh]);
  return <section className="panel">
    <h2>Mes accès</h2>
    <p>Jetons individuels — seules leurs métadonnées sont affichées. Aucun secret n’est enregistré dans le navigateur.</p>
    <p>Pour renouveler ou révoquer un jeton, contactez l’administrateur OIP. Les changements prennent effet immédiatement.</p>
    {loading && <p role="status">Chargement…</p>}
    {error && <p role="alert">{error}</p>}
    {!loading && data && <>
      <table><thead><tr><th>Usage</th><th>Identifiant</th><th>Statut</th><th>Expiration (UTC)</th></tr></thead>
        <tbody>{data.items.map(item => <tr key={item.id}>
          <td>{item.label}{item.current ? ' (jeton actuel)' : ''}</td>
          <td><code>{item.id}</code></td>
          <td>{item.status}</td>
          <td>{new Date(item.expires_at).toLocaleString('fr-FR', { timeZone: 'UTC' })}</td>
        </tr>)}</tbody>
      </table>
      {data.items.length === 0 && <p>Aucun jeton visible.</p>}
      <div className="panel-actions">
        <button type="button" disabled={page === 0} onClick={() => setPage(Math.max(0, page - 1))}>Précédent</button>
        <span>{data.total} jeton(s)</span>
        <button type="button" disabled={(page + 1) * 20 >= data.total} onClick={() => setPage(page + 1)}>Suivant</button>
      </div>
    </>}
  </section>;
}
