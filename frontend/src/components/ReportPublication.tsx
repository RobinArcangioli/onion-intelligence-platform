import { useState } from 'react';
import { api, request } from '../lib/api';
import { totalLabels } from '../lib/publicApi';
import type { PublicationPreview } from '../lib/publicApi';
import { readableError } from '../lib/util';
import { DateCell, Icon } from './ui';

export function ReportPublication({token,reportId,onNotice}:{token:string;reportId:string;onNotice:(text:string,kind?:'success'|'error')=>void}){
  const [open,setOpen]=useState(false);const [preview,setPreview]=useState<PublicationPreview|null>(null);
  const [busy,setBusy]=useState(false);const [error,setError]=useState('');
  async function show(){setOpen(true);setPreview(null);setError('');setBusy(true);
    try{setPreview(await api.get<PublicationPreview>(token,`/api/v1/reports/${reportId}/publication-preview`));}
    catch(e){setError(readableError(e));}finally{setBusy(false);}}
  async function publish(){if(!preview)return;setBusy(true);setError('');
    try{const result=await api.post<{publication_id:string}>(token,`/api/v1/reports/${reportId}/publication`,{expected_digest:preview.digest});setPreview({...preview,publication_id:result.publication_id});onNotice('Version agrégée publiée dans la vitrine.');}
    catch(e){setError(readableError(e));}finally{setBusy(false);}}
  async function withdraw(){if(!preview?.publication_id)return;setBusy(true);setError('');
    try{await request(token,`/api/v1/reports/${reportId}/publication/${preview.publication_id}`,{method:'DELETE'});setPreview({...preview,publication_id:null});onNotice('Rapport retiré de la vitrine.');}
    catch(e){setError(readableError(e));}finally{setBusy(false);}}
  return <><button className="tiny-btn" onClick={show}><Icon name="globe" size={14}/> Vitrine</button>
    {open&&<div className="modal-shade"><section className="modal" role="dialog" aria-modal="true" aria-label="Publication publique du rapport"><div className="modal-head"><div><p className="eyebrow">PUBLICATION CONTRÔLÉE</p><h2>Version publique du rapport</h2></div><button className="icon-button" disabled={busy} aria-label="Fermer" onClick={()=>setOpen(false)}><Icon name="x"/></button></div>
      <div className="publication-body"><p>Seuls la période et les compteurs ci-dessous seront publics. Les lignes détaillées, identifiants, adresses, notes et informations internes sont exclus.</p>
        {error&&<p role="alert" className="inline-error">{error}</p>}{busy&&!preview&&<p role="status">Chargement de l’aperçu…</p>}
        {preview&&<><p>Du <DateCell value={preview.content.period_start}/> au <DateCell value={preview.content.period_end}/></p><dl className="public-totals">{Object.entries(totalLabels).map(([key,label])=><div key={key}><dt>{label}</dt><dd>{preview.content.totals[key as keyof typeof totalLabels]}</dd></div>)}</dl>
          <p className="muted small">{preview.content.disclaimer}</p><p role="status">{preview.publication_id?'Ce rapport possède une version publique.':'Ce rapport n’est pas publié.'}</p>
          <div className="form-actions">{preview.publication_id?<button className="btn btn-secondary" disabled={busy} onClick={withdraw}>Retirer de la vitrine</button>:<button className="btn btn-primary" disabled={busy} onClick={publish}>Publier ces compteurs</button>}</div></>}
      </div></section></div>}
  </>;
}
