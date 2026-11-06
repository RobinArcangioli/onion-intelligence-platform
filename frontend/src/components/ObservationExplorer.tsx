/** Read-only analyst explorer: deliberately limited to retained metadata. */
import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { api } from '../lib/api';
import type { Observation, Page, Source } from '../lib/types';
import { dateTime, query, readableError } from '../lib/util';
import { DateCell, Empty, Icon, Mono, PageHead, Pager, Panel, Status } from './ui';

type Item = Observation & {source_name:string;source_category:string};
type Provenance = {
  page: {id: string; url: string} | null;
  observation:Observation; source:{id:string;name:string|null;category:string|null};
  job:{id:string;status:string|null;started_at:string|null;finished_at:string|null};
  previous_observation_id:string|null; hash_changed:boolean|null;
  metadata_changes:Record<string,{before:string|number;after:string|number}>;
  comparison_scope:string;limitations:string;
};
const pageSize=20;

export function ObservationExplorer({token,refresh}: {token:string;refresh:number}) {
  const [draft,setDraft]=useState(''); const [text,setText]=useState('');
  const [source,setSource]=useState(''); const [status,setStatus]=useState('');
  const [since,setSince]=useState(''); const [until,setUntil]=useState('');
  const [offset,setOffset]=useState(0);
  const [data,setData]=useState<Page<Item>>({items:[],offset:0,total:0,limit:pageSize});
  const [sources,setSources]=useState<Source[]>([]); const [loading,setLoading]=useState(true);
  const [error,setError]=useState(''); const [details,setDetails]=useState<Provenance|null>(null);
  const [detailsLoading,setDetailsLoading]=useState(false);
  useEffect(()=>{ let alive=true;
    api.get<Page<Source>>(token,'/api/v1/sources?limit=100').then(p=>{if(alive)setSources(p.items);})
      .catch(()=>{/* Search works without source picker. */});
    return ()=>{alive=false;};
  },[token,refresh]);
  const path='/api/v1/observations/search'+query({limit:pageSize,offset,source_id:source,change_status:status,q:text,
    since:since?new Date(since).toISOString():undefined,until:until?new Date(until).toISOString():undefined});
  useEffect(()=>{let alive=true;setLoading(true);setError('');
    api.get<Page<Item>>(token,path).then(r=>{if(alive)setData(r);})
      .catch(e=>{if(alive)setError(readableError(e));})
      .finally(()=>{if(alive)setLoading(false);});
    return ()=>{alive=false;};
  },[token,path,refresh]);
  async function show(item:Item){setError('');setDetailsLoading(true);
    try {setDetails(await api.get<Provenance>(token,`/api/v1/observations/${item.id}/provenance`));}
    catch(e){setError(readableError(e));}finally{setDetailsLoading(false);}
  }
  function submit(e:FormEvent){e.preventDefault();setOffset(0);setText(draft.trim());}
  return <><PageHead eyebrow="INVESTIGATION / OBSERVATIONS" title="Historique des observations"
    description="Recherchez les métadonnées conservées, puis vérifiez la provenance et les changements d’empreinte."/>
    <Panel title="Recherche documentaire" kicker="METADATA ONLY" action={<span className="counter">{data.total} résultats</span>}>
      <form className="filter-row" onSubmit={submit}>
        <label className="search-box"><Icon name="search" size={18}/><input aria-label="Rechercher dans les titres et descriptions" value={draft} maxLength={120} placeholder="Titre ou description (pas le texte des pages)" onChange={e=>setDraft(e.target.value)}/><button type="submit">Chercher</button></label>
        <label className="select-wrap"><span className="sr-only">Source</span><select aria-label="Source" value={source} onChange={e=>{setSource(e.target.value);setOffset(0);}}><option value="">Toutes les sources</option>{sources.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
        <label className="select-wrap"><span className="sr-only">Changement</span><select aria-label="Changement" value={status} onChange={e=>{setStatus(e.target.value);setOffset(0);}}><option value="">Tous les changements</option>{['FIRST_SEEN','MODIFIED','UNCHANGED','UNKNOWN'].map(s=><option key={s} value={s}>{s}</option>)}</select></label>
        <label>Depuis (UTC/local)<input aria-label="Depuis" type="datetime-local" value={since} onChange={e=>{setSince(e.target.value);setOffset(0);}}/></label>
        <label>Avant (UTC/local)<input aria-label="Avant" type="datetime-local" value={until} onChange={e=>{setUntil(e.target.value);setOffset(0);}}/></label>
      </form>
      {error&&<div role="alert" className="inline-error">{error}</div>}
      <div className="table-scroller"><table><thead><tr><th>Source</th><th>Titre</th><th>Statut</th><th>Empreinte SHA-256</th><th>Observé</th><th>Provenance</th></tr></thead>
        <tbody>{data.items.map(r=><tr key={r.id}><td>{r.source_name}<br/><small>{r.source_category}</small></td><td>{r.title||'—'}</td><td><Status value={r.change_status}/></td><td><Mono value={r.text_sha256}/></td><td><DateCell value={r.created_at}/></td><td><button className="tiny-btn" onClick={()=>void show(r)} disabled={detailsLoading}>Comparer</button></td></tr>)}
        {!data.items.length&&<tr><td colSpan={6}><Empty title={loading?'Chargement…':'Aucune observation'} text="Affinez les filtres ou vérifiez la période."/></td></tr>}</tbody></table></div>
      <Pager total={data.total} offset={offset} pageSize={pageSize} onChange={setOffset}/>
      <p className="page-footnote">La recherche porte uniquement sur les titres et descriptions conservés. Aucun texte complet, média ou contenu HTML n’est enregistré ni recherché.</p>
    </Panel>
    {details&&<div className="modal-shade" onMouseDown={e=>{if(e.target===e.currentTarget)setDetails(null);}}>
      <section className="modal modal-wide" role="dialog" aria-modal="true" aria-label="Provenance de l'observation"><div className="modal-head"><div><p className="eyebrow">PROVENANCE / CHANGE TRACE</p><h2>Comparaison des observations</h2></div><button className="icon-button" aria-label="Fermer" onClick={()=>setDetails(null)}><Icon name="x"/></button></div>
        <p>Source : {details.source.name||details.source.id} · Job : <Mono value={details.job.id}/> · État : {details.job.status||'inconnu'}</p>
        <p>Observation : <Mono value={details.observation.id}/> · {dateTime(details.observation.created_at)}</p>
        <p>Précédente : {details.previous_observation_id?<Mono value={details.previous_observation_id}/>: 'aucune'}</p>
        <p>Empreinte : <strong>{details.hash_changed===null?'première observation':details.hash_changed?'modifiée':'identique'}</strong></p>
        <p className="small">{details.observation.origin === 'OPERATOR_CAPTURE' ? 'Capture opérateur' : 'Collecte via Tor'}
          {details.page && <> · <Mono value={details.page.url}/></>}</p>
        <div className="table-scroller"><table><thead><tr><th>Champ conservé</th><th>Avant</th><th>Après</th></tr></thead><tbody>{Object.entries(details.metadata_changes).map(([key,v])=><tr key={key}><td>{key}</td><td>{String(v.before)}</td><td>{String(v.after)}</td></tr>)}{!Object.keys(details.metadata_changes).length&&<tr><td colSpan={3}>Aucune différence de métadonnées comparable.</td></tr>}</tbody></table></div>
        <p className="page-footnote">{details.limitations}</p>
      </section></div>}
  </>;
}
