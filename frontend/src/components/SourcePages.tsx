import { useEffect, useRef, useState } from 'react';
import { api } from '../lib/api';
import type { CollectionProgress, Observation, Page, Source, SourcePage } from '../lib/types';
import { collectionMessage } from '../lib/manualCollection';
import { readableError } from '../lib/util';
import { Icon, Pager, Status } from './ui';

const pageSize = 25;

export function SourcePages({ token, source, canEdit, onClose }: {
  token: string;
  source: Source;
  canEdit: boolean;
  onClose: () => void;
}) {
  const endpoint = `/api/v1/sources/${source.id}/pages`;
  const [pages, setPages] = useState<Page<SourcePage>>({ items: [], total: 0, offset: 0, limit: pageSize });
  const [progress, setProgress] = useState<CollectionProgress | null>(null);
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const [target, setTarget] = useState<SourcePage | null>(null);
  const [url, setUrl] = useState('');
  const [text, setText] = useState('');
  const requestId = useRef('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  useEffect(() => {
    let active = true;
    let timer: number;
    setLoading(true);
    async function refresh(initial: boolean) {
      try {
        const [list, current] = await Promise.all([
          api.get<Page<SourcePage>>(token, `${endpoint}?limit=${pageSize}&offset=${offset}`),
          api.get<CollectionProgress>(token, `/api/v1/sources/${source.id}/collection/progress`),
        ]);
        if (active) { setPages(list); setProgress(current); }
      } catch (err) {
        if (active && initial) setError(readableError(err));
      } finally {
        if (active) {
          setLoading(false);
          timer = window.setTimeout(() => { void refresh(false); }, 4000);
        }
      }
    }
    void refresh(true);
    return () => { active = false; window.clearTimeout(timer); };
  }, [endpoint, offset, revision, source.id, token]);

  async function save(analyze: boolean) {
    if (busy || !url.trim() || (analyze && !text.trim())) return;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      if (analyze) {
        requestId.current ||= crypto.randomUUID();
        const result = await api.post<Observation>(token, endpoint + '/capture', {
          url, text, request_id: requestId.current,
        });
        setNotice(`Analyse terminée. ${result.keyword_hits} occurrence(s) détectée(s). Observation ${result.id}.`);
      } else {
        await api.post<SourcePage>(token, endpoint, { url });
        setNotice('URL enregistrée dans ce groupe.');
      }
      setUrl('');
      setText('');
      requestId.current = '';
      setRevision(value => value + 1);
    } catch (err) {
      setError(readableError(err));
    } finally {
      setBusy(false);
    }
  }

  async function remove(page: SourcePage) {
    if (busy || !window.confirm('Retirer cette URL des prochaines veilles ?')) return;
    setBusy(true);
    setError('');
    try {
      await api.delete(token, `${endpoint}/${page.id}`);
      if (pages.items.length === 1 && offset > 0) setOffset(offset - pageSize);
      setRevision(value => value + 1);
      setNotice('URL retirée du groupe.');
    } catch (err) {
      setError(readableError(err));
    } finally {
      setBusy(false);
    }
  }

  return <div className="modal-shade">
    <section className="modal modal-wide" role="dialog" aria-modal="true" aria-label={`URL de ${source.name}`}>
      <div className="modal-head">
        <div><p className="eyebrow">GROUPE DE SOURCES</p><h2>{source.name}</h2></div>
        <button className="icon-button" aria-label="Fermer" disabled={busy} onClick={onClose}><Icon name="x"/></button>
      </div>
      {error && <p className="inline-error" role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      {progress && progress.total > 0 && <section className="source-page-visit" aria-label="Progression de la veille">
        <p><strong>{progress.completed + progress.failed} / {progress.total} URL traitées</strong>
          {' · '}{progress.completed} réussie(s) · {progress.failed} en échec · {progress.waiting} en attente</p>
        {progress.running_url && <p>URL en cours <code>{progress.running_url}</code></p>}
        {progress.restriction && <p>{collectionMessage(progress.restriction, progress.retry_at)}</p>}
      </section>}
      {loading && <p role="status">Chargement des URL…</p>}
      {!loading && pages.items.length === 0 && <p>Aucune URL active dans ce groupe.</p>}
      <ul className="source-page-list">
        {pages.items.map(page => <li key={page.id}>
          <code>{page.url}</code>
          {page.status && <span>
            <Status value={page.status === 'WAITING' ? 'PENDING' : page.status}/>
            {page.error_code && <span className="muted small"> {collectionMessage(page.error_code)}</span>}
          </span>}
          <div className="row-actions">
            <button className="tiny-btn" disabled={busy} onClick={() => setTarget(page)}>Visiter l’URL</button>
            {canEdit && <button className="tiny-btn caution" disabled={busy} onClick={() => void remove(page)}>Retirer</button>}
          </div>
        </li>)}
      </ul>
      <Pager total={pages.total} offset={offset} pageSize={pageSize} onChange={setOffset}/>
      {target && <section className="source-page-visit" aria-label="Confirmer l’ouverture dans Tor Browser">
        <p>Ouvrir cette adresse dans Tor Browser ?</p>
        <p><code>{target.url}</code></p>
        <div className="row-actions">
          <a className="btn btn-primary" href={`oip-tor:${encodeURIComponent(target.url)}`}
             onClick={() => { if (canEdit) { setUrl(target.url); requestId.current = ''; } }}>
            Ouvrir dans Tor Browser
          </a>
          <button className="btn btn-secondary" onClick={() => setTarget(null)}>Fermer</button>
        </div>
        <p className="muted small">Si le lanceur local est indisponible, copie cette adresse dans Tor Browser.</p>
      </section>}
      {canEdit && <form className="form-grid" onSubmit={event => { event.preventDefault(); }}>
        <label>URL Onion finale<input required value={url} maxLength={255} spellCheck={false}
          disabled={busy} onChange={event => { setUrl(event.target.value); requestId.current = ''; }}/></label>
        <label>Texte visible dans Tor Browser<textarea value={text} rows={5} maxLength={100000}
          disabled={busy} onChange={event => { setText(event.target.value); requestId.current = ''; }}/></label>
        <div className="form-actions">
          <button type="button" className="btn btn-secondary" disabled={busy || !url.trim()}
            onClick={() => void save(false)}>Ajouter l’URL</button>
          <button type="button" className="btn btn-primary"
            disabled={busy || !source.is_active || !source.approved_for_collection || !url.trim() || !text.trim()}
            onClick={() => void save(true)}>Ajouter et analyser maintenant</button>
        </div>
      </form>}
    </section>
  </div>;
}
