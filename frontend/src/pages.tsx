import { useEffect, useState } from 'react';
import type { FormEvent, ReactNode } from 'react';
import { api, downloadExport } from './lib/api';
import { canCollectNow, jobLabel } from './lib/manualCollection';
import type { Alert, Audit, Classification, Correlation, Discovery, Indicator, Job, Observation, Page, Report, Rule, Source, Watchlist } from './lib/types';
import { APPROVAL, NOTE, dateTime, limit, localDateInput, priorDays, query, readableError, shortNumber } from './lib/util';
import { DateCell, Empty, Icon, Mono, PageHead, Pager, Panel, Score, Status } from './components/ui';

type Shared = {token:string;refresh:number;onNotice:(text:string,kind?:'success'|'error')=>void};
function useList<T>(token:string, endpoint:string, refresh:number) {
  const [data,setData]=useState<Page<T>>({items:[],total:0,limit,offset:0});
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState('');
  useEffect(()=>{ let alive=true; setLoading(true);setError('');
    if (!endpoint) { setData({items:[],total:0,limit,offset:0}); setLoading(false); return ()=>{alive=false;}; }
    api.get<Page<T>>(token,endpoint).then(value=>{if(alive)setData(value);})
      .catch(err=>{if(alive)setError(readableError(err));})
      .finally(()=>{if(alive)setLoading(false);});
    return ()=>{alive=false;};
  },[token,endpoint,refresh]);
  return {data,loading,error};
}
function Failure({text}: {text:string}) {return text?<div role="alert" className="inline-error"><Icon name="x" size={17}/>{text}</div>:null;}
function TableShell({children}: {children:ReactNode}) {return <div className="table-scroller"><table>{children}</table></div>}
function tdEmpty(colSpan:number,loading:boolean) {return <tr><td colSpan={colSpan}><Empty title={loading?'Chargement des données…':'Aucun résultat'} text={loading?'Lecture des données OIP en cours.':'Aucune donnée pour les filtres sélectionnés.'}/></td></tr>}
function Select({value,change,options,label}: {value:string;change:(v:string)=>void;options:{value:string;label:string}[];label:string}) {return <label className="select-wrap"><span className="sr-only">{label}</span><select value={value} onChange={e=>change(e.target.value)}>{options.map(x=><option key={x.value} value={x.value}>{x.label}</option>)}</select><Icon name="chevron" size={13}/></label>}
async function execute(task:()=>Promise<unknown>,onNotice:Shared['onNotice'],success:string,onSuccess:()=>void) {try {await task();onSuccess();onNotice(success);}catch(e){onNotice(readableError(e),'error');}}

export function Overview({token,refresh,onNotice: _notice,go}: Shared & {go:(next:'sources'|'discoveries'|'alerts'|'reports')=>void}) {
  const [stats,setStats]=useState<{sources:number;observations:number;discoveries:number;alerts:number;cti:number;reports:number;watchlists:number}|null>(null);
  const [recent,setRecent]=useState<Observation[]>([]);
  const [lastAlerts,setLastAlerts]=useState<Alert[]>([]);
  const [jobs,setJobs]=useState<Job[]>([]);
  const [error,setError]=useState('');const [loading,setLoading]=useState(true);
  useEffect(()=>{let live=true;setLoading(true);setError('');
    Promise.all([
      api.get<Page<Source>>(token,'/api/v1/sources?limit=1'),
      api.get<Page<Observation>>(token,'/api/v1/collection/observations?limit=50'),
      api.get<Page<Discovery>>(token,'/api/v1/collection/discoveries?status=PENDING&limit=1'),
      api.get<Page<Alert>>(token,'/api/v1/alerts?status=OPEN&limit=5'),
      api.get<Page<Classification>>(token,'/api/v1/cti/classifications?limit=1'),
      api.get<Page<Report>>(token,'/api/v1/reports?limit=1'),
      api.get<Page<Watchlist>>(token,'/api/v1/watchlists?limit=1'),
      api.get<Page<Job>>(token,'/api/v1/collection/jobs?limit=5'),
    ]).then(([s,o,d,a,c,r,w,j])=>{if(!live)return;
      setStats({sources:s.total,observations:o.total,discoveries:d.total,alerts:a.total,cti:c.total,reports:r.total,watchlists:w.total});setRecent(o.items);setLastAlerts(a.items);setJobs(j.items);
    }).catch(e=>{if(live)setError(readableError(e));}).finally(()=>{if(live)setLoading(false);});
    return ()=>{live=false;};
  },[token,refresh]);
  const cards=[
    {label:'Sources surveillées',value:stats?.sources,icon:'layers' as const,tone:'mint',link:'sources' as const,footer:'Registre autorisé'},
    {label:'Pages observées',value:stats?.observations,icon:'activity' as const,tone:'blue',link:'sources' as const,footer:'Métadonnées enregistrées'},
    {label:'Découvertes à revoir',value:stats?.discoveries,icon:'radar' as const,tone:'amber',link:'discoveries' as const,footer:'Validation requise'},
    {label:'Alertes ouvertes',value:stats?.alerts,icon:'bell' as const,tone:'rose',link:'alerts' as const,footer:'Action opérateur'},
  ];
  const today=new Date();const histogram=Array.from({length:7},(_,i)=>{const d=new Date(today);d.setHours(0,0,0,0);d.setDate(d.getDate()-(6-i));const next=new Date(d);next.setDate(next.getDate()+1);
    return {label:new Intl.DateTimeFormat('fr-FR',{weekday:'short'}).format(d),count:recent.filter(o=>{const t=new Date(o.created_at).getTime();return t>=d.getTime()&&t<next.getTime();}).length};});
  const max=Math.max(1,...histogram.map(x=>x.count));
  return <><PageHead eyebrow="OVERVIEW / LIVE DATA" title="Tableau de bord" description="Vue d'ensemble de votre veille et de vos observations collectées." actions={<span className="live-tag"><span className="online-dot"/> DATA LIVE</span>}/>
    <Failure text={error}/>
    <div className="stats-grid">{cards.map(card=><button className={`stat-card stat-${card.tone}`} key={card.label} onClick={()=>go(card.link)}><div className="stat-top"><span>{card.label}</span><span className="stat-icon"><Icon name={card.icon}/></span></div><strong>{loading?'…':shortNumber(card.value||0)}</strong><div className="stat-bottom"><span>{card.footer}</span><Icon name="arrow" size={15}/></div></button>)}</div>
    <div className="overview-grid">
      <Panel title="Activité de collecte" kicker="7 DERNIERS JOURS" action={<span className="panel-caption">Échantillon : 50 dernières observations</span>}>
        <div className="chart-area">{histogram.map((x,i)=><div className="chart-column" key={i}><span className="chart-count">{x.count||''}</span><div className="chart-column-bg"><div className="chart-bar" style={{height:`${x.count?Math.max(7,100*x.count/max):0}%`}}/></div><span className="chart-label">{x.label}</span></div>)}</div>
        <div className="chart-note"><span className="chart-legend-dot"/>Observations des 7 derniers jours dans l'échantillon chargé</div>
      </Panel>
      <Panel title="Statut opérationnel" kicker="SYSTEM / STATUS">
        <div className="health-list"><div><span className="health-icon"><Icon name="database"/></span><span><strong>Registre de sources</strong><small>API connectée</small></span><Status value="ACTIVE"/></div>
          <div><span className="health-icon"><Icon name="shield"/></span><span><strong>Collecte contrôlée</strong><small>Activation manuelle requise</small></span><span className="quiet-tag">MANUEL</span></div>
          <div><span className="health-icon"><Icon name="eye"/></span><span><strong>Règles de veille</strong><small>{stats?.watchlists||0} watchlist(s)</small></span><Status value="ACTIVE"/></div>
          <div><span className="health-icon"><Icon name="file"/></span><span><strong>Rapports archivés</strong><small>{stats?.reports||0} rapport(s)</small></span><span className="quiet-tag">LOCAL</span></div></div>
        <div className="health-disclaimer"><Icon name="shield" size={15}/> L'état Tor n'est pas vérifié par ce tableau.</div>
      </Panel>
    </div>
    <div className="overview-grid overview-bottom">
      <Panel title="Dernières observations" kicker="COLLECTION / HISTORY" action={<button className="text-button" onClick={()=>go('sources')}>Voir les sources <Icon name="arrow" size={14}/></button>}>
        {recent.length?<div className="feed">{recent.slice(0,5).map(item=><div className="feed-item" key={item.id}><span className="feed-symbol"><Icon name="activity" size={17}/></span><div><strong>{item.title||'Page sans titre'}</strong><small><Mono value={item.source_id}/> · {dateTime(item.created_at)}</small></div><Score value={item.relevance_score}/></div>)}</div>:<Empty title="Aucune observation" text="L'historique apparaîtra après une collecte autorisée."/>}
      </Panel>
      <Panel title="Alertes récentes" kicker="PRIORITÉ / OPEN" action={<button className="text-button" onClick={()=>go('alerts')}>Toutes les alertes <Icon name="arrow" size={14}/></button>}>
        {lastAlerts.length?<div className="feed">{lastAlerts.map(item=><div className="feed-item" key={item.id}><span className="feed-symbol feed-alert"><Icon name="bell" size={17}/></span><div><strong>{item.event_type.replaceAll('_',' ')}</strong><small>{item.signal_code} · {dateTime(item.created_at)}</small></div><Status value={item.priority}/></div>)}</div>:<Empty title="Aucune alerte ouverte" text="Les prochaines détections apparaîtront ici."/>}
      </Panel>
    </div>
    {jobs.length>0&&<p className="page-footnote">Dernier job : {dateTime(jobs[0].created_at)} · <Status value={jobs[0].status}/></p>}
  </>;
}

export function Sources({token,refresh,onNotice,role}:Shared & {role:string}) {
  const [search,setSearch]=useState('');const [applied,setApplied]=useState('');const [active,setActive]=useState('');const [offset,setOffset]=useState(0);const [seq,setSeq]=useState(0);
  const [showForm,setShowForm]=useState(false);const [edit,setEdit]=useState<Source|null>(null);const [history,setHistory]=useState<{source:Source;items:Audit[]}|null>(null);const [busy,setBusy]=useState(false);
  const [name,setName]=useState('');const [url,setUrl]=useState('');const [desc,setDesc]=useState('');const [priority,setPriority]=useState(3);const [consent,setConsent]=useState(false);
  const endpoint='/api/v1/sources'+query({limit,offset,q:applied,active:active===''?undefined:active==='true'});
  const {data,loading,error}=useList<Source>(token,endpoint,refresh+seq);
  const [latest,setLatest]=useState<Record<string,Job>>({});
  const [enqueuing,setEnqueuing]=useState<string[]>([]);
  const sourceIds=data.items.map(s=>s.id).join(',');
  useEffect(()=>{
    const ids=sourceIds.split(',').filter(Boolean);
    let alive=true;
    if(!ids.length){setLatest({});return ()=>{alive=false;};}
    const endpoint='/api/v1/collection/latest?'+ids.map(id=>'source_ids='+encodeURIComponent(id)).join('&');
    async function update(){try{
      const jobs=await api.get<Job[]>(token,endpoint);
      if(alive)setLatest(Object.fromEntries(jobs.map(j=>[j.source_id,j])));
    }catch{/* The source list handles API errors; don't repeatedly toast polling failures. */}}
    void update();
    const poll=window.setInterval(()=>{void update();},4000);
    return ()=>{alive=false;window.clearInterval(poll);};
  },[token,sourceIds,refresh,seq]);
  const reload=()=>setSeq(n=>n+1);
  async function manualCollection(s:Source){
    if(!canCollectNow(s,latest[s.id]?.status,enqueuing.includes(s.id),role))return;
    setEnqueuing(current=>[...current,s.id]);
    try {
      const job=await api.post<Job>(token,`/api/v1/sources/${s.id}/collection/run`,{reason:NOTE});
      setLatest(current=>({...current,[s.id]:job}));
      onNotice('Collecte ajoutée à la file. Le worker Tor la traitera dès qu’il sera actif.');
    }catch(err){onNotice(readableError(err),'error');reload();}
    finally{setEnqueuing(current=>current.filter(id=>id!==s.id));}
  }
  function resetForm(){setName('');setUrl('');setDesc('');setPriority(3);setConsent(false);setEdit(null);setShowForm(false);}
  function openEdit(s:Source){setEdit(s);setName(s.name);setDesc(s.description);setPriority(s.priority);setShowForm(true);}
  async function submit(e:FormEvent){e.preventDefault();setBusy(true);
    try {
      if(edit){await api.patch<Source>(token,`/api/v1/sources/${edit.id}`,{name,description:desc,priority,reason:NOTE});}
      else {if(!consent)throw Error('Une autorisation explicite est nécessaire.');
        await api.post<Source>(token,'/api/v1/sources',{url,name,description:desc,priority,authorization_confirmed:true,authorization_note:APPROVAL});}
      onNotice(edit?'Source mise à jour.':'Source enregistrée.');resetForm();reload();
    }catch(err){onNotice(readableError(err),'error');}finally{setBusy(false);}
  }
  async function sourceAction(s:Source,what:'activate'|'deactivate'|'approve'|'revoke'|'enable'|'disable'){
    if((what==='revoke'||what==='enable')&&!window.confirm(what==='revoke'?'Révoquer l’autorisation de cette source ?':'Autoriser la collecte future de cette source ?'))return;
    const path=what==='enable'||what==='disable'?`/api/v1/sources/${s.id}/collection/${what}`:`/api/v1/sources/${s.id}/${what}`;
    const body=what==='approve'?{authorization_confirmed:true,authorization_note:APPROVAL}:{reason:NOTE};
    await execute(()=>api.post(token,path,body),onNotice,'Statut mis à jour.',reload);
  }
  async function showHistory(s:Source){try{const value=await api.get<Page<Audit>>(token,`/api/v1/sources/${s.id}/history?limit=30`);setHistory({source:s,items:value.items});}catch(e){onNotice(readableError(e),'error');}}
  return <><PageHead eyebrow="SOURCE REGISTRY / MANAGEMENT" title="Sources Onion" description="Périmètre de surveillance. Aucune source n'est explorée sans autorisation." actions={<><button className="btn btn-secondary" onClick={()=>execute(()=>downloadExport(token,'/api/v1/sources/export.csv','oip-sources.csv'),onNotice,'Export téléchargé.',()=>{})}><Icon name="download"/> Export CSV</button><button className="btn btn-primary" onClick={()=>{resetForm();setShowForm(true);}}><Icon name="plus"/> Ajouter une source</button></>}/>
    <Panel title="Registre des sources" kicker="AUTHORIZED SCOPE" action={<span className="counter">{data.total} sources</span>}>
      <div className="filter-row"><form className="search-box" onSubmit={e=>{e.preventDefault();setOffset(0);setApplied(search.trim());}}><Icon name="search" size={18}/><input aria-label="Recherche source" placeholder="Rechercher nom, URL ou description" value={search} onChange={e=>setSearch(e.target.value)}/><button type="submit">Chercher</button></form>
        <Select value={active} change={v=>{setOffset(0);setActive(v);}} label="Filtrer statut" options={[{value:'',label:'Tous les statuts'},{value:'true',label:'Actives'},{value:'false',label:'Inactives'}]}/></div>
      <Failure text={error}/>
      <p className="page-footnote">La collecte est ponctuelle : le service <code>queue_worker</code> doit être démarré dans le profil Tor. Les statuts sont actualisés toutes les 4 secondes. Aucun lien découvert n’est visité.</p>
      <TableShell><thead><tr><th>Source</th><th>Catégorie</th><th>État</th><th>Autorisation</th><th>Collecte</th><th>Priorité</th><th>Actions</th></tr></thead><tbody>{data.items.map(s=><tr key={s.id}><td><div className="cell-main"><strong>{s.name}</strong><Mono value={s.canonical_url}/></div></td><td><span className="category-tag">{s.category}</span></td><td><Status value={s.is_active}/></td><td><Status value={s.approved_for_collection?'APPROVED':'REVOKED'}/></td><td><div className="cell-main"><Status value={s.collection_enabled?'ACTIVE':'DISABLED'}/>{latest[s.id]&&<span className="muted small" aria-label={`Dernière collecte : ${latest[s.id].status}`}><Status value={latest[s.id].status}/> · {dateTime(latest[s.id].created_at)}</span>}</div></td><td><span className="priority-index">P{s.priority}</span></td><td><div className="row-actions"><button className="tiny-btn collect-now-btn" disabled={!canCollectNow(s,latest[s.id]?.status,enqueuing.includes(s.id),role)} onClick={()=>manualCollection(s)} aria-label={`Collecter maintenant : ${s.name}`}>{enqueuing.includes(s.id)?'Ajout…':jobLabel(latest[s.id]?.status)}</button><button className="tiny-btn" onClick={()=>openEdit(s)}>Modifier</button><button className="tiny-btn" onClick={()=>showHistory(s)}>Audit</button>{s.is_active?<button className="tiny-btn" onClick={()=>sourceAction(s,'deactivate')}>Pause</button>:<button className="tiny-btn" onClick={()=>sourceAction(s,'activate')}>Activer</button>}{s.approved_for_collection?<button className="tiny-btn caution" onClick={()=>sourceAction(s,'revoke')}>Révoquer</button>:<button className="tiny-btn" onClick={()=>sourceAction(s,'approve')}>Approuver</button>}{s.collection_enabled?<button className="tiny-btn caution" onClick={()=>sourceAction(s,'disable')}>Stop collecte</button>:<button className="tiny-btn" disabled={!s.is_active||!s.approved_for_collection} onClick={()=>sourceAction(s,'enable')}>Autoriser collecte</button>}</div></td></tr>)}
        {!data.items.length&&tdEmpty(7,loading)}</tbody></TableShell>
      <Pager total={data.total} offset={offset} pageSize={limit} onChange={setOffset}/>
    </Panel>
    {showForm&&<div className="modal-shade" onMouseDown={e=>{if(e.target===e.currentTarget)resetForm();}}><section className="modal" role="dialog" aria-modal="true" aria-label={edit?'Modifier la source':'Ajouter une source'}><div className="modal-head"><div><p className="eyebrow">SOURCE REGISTRY</p><h2>{edit?'Modifier la source':'Nouvelle source Onion'}</h2></div><button className="icon-button" aria-label="Fermer" onClick={resetForm}><Icon name="x"/></button></div>
      <form onSubmit={submit} className="form-grid"><label>Nom<input required maxLength={160} value={name} onChange={e=>setName(e.target.value)} placeholder="Nom de la source"/></label>{!edit&&<label>Adresse Onion v3<input required value={url} onChange={e=>setUrl(e.target.value)} placeholder="http://...onion/" spellCheck={false}/></label>}
        <label>Description<textarea maxLength={2000} rows={3} value={desc} onChange={e=>setDesc(e.target.value)} placeholder="Description facultative"/></label><label>Priorité<select value={priority} onChange={e=>setPriority(Number(e.target.value))}>{[1,2,3,4,5].map(n=><option key={n} value={n}>P{n}</option>)}</select></label>
        {!edit&&<label className="check-label"><input type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)}/><span>Je confirme l'autorisation de consultation de cette source. La collecte restera désactivée par défaut.</span></label>}
        <div className="form-actions"><button type="button" className="btn btn-secondary" onClick={resetForm}>Annuler</button><button disabled={busy||(!edit&&!consent)} className="btn btn-primary" type="submit">{busy?'Enregistrement…':'Enregistrer'}</button></div>
      </form></section></div>}
    {history&&<div className="modal-shade" onMouseDown={e=>{if(e.target===e.currentTarget)setHistory(null);}}><section className="modal modal-wide" role="dialog" aria-modal="true" aria-label="Historique de la source"><div className="modal-head"><div><p className="eyebrow">SOURCE AUDIT</p><h2>{history.source.name}</h2></div><button className="icon-button" aria-label="Fermer" onClick={()=>setHistory(null)}><Icon name="x"/></button></div>
      <div className="audit-list">{history.items.length?history.items.map(a=><div key={a.id}><span className="audit-connector"/><strong>{a.action}</strong><small>{dateTime(a.created_at)} · {typeof a.details.reason==='string'?a.details.reason:''}</small></div>):<Empty/>}</div></section></div>}
  </>;
}

export function Discoveries({token,refresh,onNotice}:Shared){
  const [status,setStatus]=useState('PENDING');const [offset,setOffset]=useState(0);const [seq,setSeq]=useState(0);
  const {data,loading,error}=useList<Discovery>(token,'/api/v1/collection/discoveries'+query({status,limit,offset}),refresh+seq);
  const review=async(item:Discovery,decision:'APPROVED'|'REJECTED')=>{
    if(!window.confirm(`${decision==='APPROVED'?'Approuver':'Rejeter'} cette découverte ? La décision n’autorise aucune collecte.`))return;
    await execute(()=>api.post(token,`/api/v1/collection/discoveries/${item.id}/review`,{decision,reason:NOTE}),onNotice,'Décision enregistrée.',()=>setSeq(n=>n+1));
  };
  return <><PageHead eyebrow="DISCOVERY / REVIEW QUEUE" title="Découvertes Onion" description="Liens détectés pendant les collectes. Une approbation ne crée jamais une source autorisée."/>
    <Panel title="File de validation" kicker="MANUAL REVIEW" action={<span className="counter">{data.total} résultats</span>}><div className="filter-row"><Select value={status} change={v=>{setStatus(v);setOffset(0);}} label="Statut découvertes" options={[{value:'',label:'Tous les statuts'},{value:'PENDING',label:'En attente'},{value:'APPROVED',label:'Approuvées'},{value:'REJECTED',label:'Rejetées'}]}/><span className="filter-hint"><Icon name="shield" size={15}/> Aucun lien n'est suivi automatiquement</span></div>
      <Failure text={error}/><TableShell><thead><tr><th>Adresse candidate</th><th>Source d'origine</th><th>Détection</th><th>Première observation</th><th>Statut</th><th>Revue</th></tr></thead><tbody>
        {data.items.map(d=><tr key={d.id}><td><div className="cell-main"><Mono value={d.target_url} title={d.target_url}/><span className="muted small">CANDIDATE / V3</span></div></td><td><Mono value={d.source_id}/></td><td><span className="category-tag">{d.evidence_kind}</span></td><td><DateCell value={d.first_seen_at}/></td><td><Status value={d.status}/></td><td><div className="row-actions">{d.status==='PENDING'?<><button className="tiny-btn tiny-approve" onClick={()=>review(d,'APPROVED')}><Icon name="check" size={13}/> Accepter</button><button className="tiny-btn caution" onClick={()=>review(d,'REJECTED')}>Rejeter</button></>:<span className="muted small">Décision enregistrée</span>}</div></td></tr>)}
        {!data.items.length&&tdEmpty(6,loading)}</tbody></TableShell><Pager total={data.total} offset={offset} pageSize={limit} onChange={setOffset}/></Panel>
    <div className="notice-strip"><Icon name="shield"/><p><strong>Règle d'engagement :</strong> l'approbation d'une découverte sert uniquement au tri documentaire. Toute collecte exige une création séparée dans le registre avec consentement explicite.</p></div>
  </>;
}

export function Threats({token,refresh,onNotice}:Shared) {
  type Mode='classifications'|'indicators'|'correlations';
  const [mode,setMode]=useState<Mode>('classifications');const [offset,setOffset]=useState(0);const [seq,setSeq]=useState(0);
  const cls=useList<Classification>(token,'/api/v1/cti/classifications'+query({limit,offset}),refresh+seq+ (mode==='classifications'?0:0));
  const inds=useList<Indicator>(token,'/api/v1/cti/indicators'+query({limit,offset}),refresh+seq);
  const co=useList<Correlation>(token,'/api/v1/cti/correlations'+query({limit,offset}),refresh+seq);
  async function review(c:Classification,decision:'ACCEPTED'|'REJECTED') {
    if(!window.confirm(`Enregistrer la revue : ${decision} ?`)) return;
    await execute(()=>api.post(token,`/api/v1/cti/classifications/${c.id}/review`,{decision,reason:NOTE}),onNotice,'Revue enregistrée.',()=>setSeq(n=>n+1));
  }
  const current=mode==='classifications'?cls:mode==='indicators'?inds:co;
  return <><PageHead eyebrow="CYBER THREAT INTELLIGENCE" title="Intelligence CTI" description="Classifications heuristiques et signaux non vérifiés. Chaque résultat exige une interprétation prudente."/>
    <div className="notice-strip"><Icon name="shield"/><p><strong>Information importante :</strong> les références observées, classifications et cooccurrences ne confirment ni attaque ni compromission.</p></div>
    <Panel title="Résultats d'analyse" kicker="OFFLINE ANALYSIS" action={<span className="counter">{current.data.total} résultats</span>}>
      <div className="tabbar" role="tablist" aria-label="Résultats CTI">{([{key:'classifications',label:'Classifications'},{key:'indicators',label:'Indicateurs'},{key:'correlations',label:'Corrélations'}] as const).map(x=><button role="tab" aria-selected={mode===x.key} className={mode===x.key?'tab-active':''} key={x.key} onClick={()=>{setMode(x.key);setOffset(0);}}>{x.label}</button>)}</div>
      <Failure text={current.error}/>
      {mode==='classifications'&&<TableShell><thead><tr><th>Catégorie proposée</th><th>Source</th><th>Confiance</th><th>Indices de règles</th><th>Statut de revue</th><th>Date</th><th>Action</th></tr></thead><tbody>{cls.data.items.map(c=><tr key={c.id}><td><div className="cell-main"><strong>{c.category.replaceAll('_',' ')}</strong><Mono value={c.observation_id}/></div></td><td><Mono value={c.source_id}/></td><td><Score value={c.confidence}/></td><td><span className="muted small">{c.evidence_codes.join(' · ')||'—'}</span></td><td><Status value={c.review_status}/></td><td><DateCell value={c.created_at}/></td><td><div className="row-actions">{!['ACCEPTED','REJECTED'].includes(c.review_status)?<><button className="tiny-btn tiny-approve" onClick={()=>review(c,'ACCEPTED')}>Valider</button><button className="tiny-btn caution" onClick={()=>review(c,'REJECTED')}>Rejeter</button></>:<span className="muted small">Terminé</span>}</div></td></tr>)}{!cls.data.items.length&&tdEmpty(7,cls.loading)}</tbody></TableShell>}
      {mode==='indicators'&&<TableShell><thead><tr><th>Type d'indice</th><th>Référence publique</th><th>Source</th><th>Confiance</th><th>Vérification</th><th>Observé</th></tr></thead><tbody>{inds.data.items.map(i=><tr key={i.id}><td><strong>{i.indicator_type.replaceAll('_',' ')}</strong></td><td><span className="mono">{i.public_reference||'—'}</span></td><td><Mono value={i.source_id}/></td><td><Score value={i.confidence}/></td><td><Status value={i.verification_status}/></td><td><DateCell value={i.created_at}/></td></tr>)}{!inds.data.items.length&&tdEmpty(6,inds.loading)}</tbody></TableShell>}
      {mode==='correlations'&&<TableShell><thead><tr><th>Observation</th><th>Source</th><th>Indicateur</th><th>Watchlist</th><th>Occurrences</th><th>Pertinence</th></tr></thead><tbody>{co.data.items.map((c,i)=><tr key={`${c.indicator_id}-${c.watchlist_id}-${i}`}><td><Mono value={c.observation_id}/></td><td><Mono value={c.source_id}/></td><td><Mono value={c.indicator_id}/></td><td><Mono value={c.watchlist_id}/></td><td>{c.occurrences}</td><td><Score value={c.relevance_score}/></td></tr>)}{!co.data.items.length&&tdEmpty(6,co.loading)}</tbody></TableShell>}
      <Pager total={current.data.total} offset={offset} pageSize={limit} onChange={setOffset}/>
    </Panel>
  </>;
}

export function Watchlists({token,refresh,onNotice}:Shared) {
  const [seq,setSeq]=useState(0);const [offset,setOffset]=useState(0);
  const {data,loading,error}=useList<Watchlist>(token,'/api/v1/watchlists'+query({limit,offset}),refresh+seq);
  const [selected,setSelected]=useState<Watchlist|null>(null);const [ruleSeq,setRuleSeq]=useState(0);
  const [newName,setNewName]=useState('');const [phrase,setPhrase]=useState('');const [weight,setWeight]=useState(10);const [busy,setBusy]=useState(false);
  const rules=useList<Rule>(token, selected?`/api/v1/watchlists/${selected.id}/rules?limit=100`:'',refresh+ruleSeq);
  async function addWatchlist(e:FormEvent){e.preventDefault();setBusy(true);
    try{await api.post(token,'/api/v1/watchlists',{name:newName});setNewName('');setSeq(n=>n+1);onNotice('Watchlist créée.');}
    catch(e){onNotice(readableError(e),'error');}finally{setBusy(false);}
  }
  async function addRule(e:FormEvent){e.preventDefault();if(!selected)return;setBusy(true);
    try{await api.post(token,`/api/v1/watchlists/${selected.id}/rules`,{phrase,weight});setPhrase('');setRuleSeq(n=>n+1);onNotice('Règle ajoutée.');}
    catch(e){onNotice(readableError(e),'error');}finally{setBusy(false);}
  }
  async function toggleWatchlist(item:Watchlist){await execute(()=>api.patch(token,`/api/v1/watchlists/${item.id}`,{is_active:!item.is_active,reason:NOTE}),onNotice,'Statut modifié.',()=>setSeq(n=>n+1));if(selected?.id===item.id)setSelected({...item,is_active:!item.is_active});}
  async function toggleRule(item:Rule){await execute(()=>api.patch(token,`/api/v1/watchlist-rules/${item.id}`,{is_active:!item.is_active,reason:NOTE}),onNotice,'Règle mise à jour.',()=>setRuleSeq(n=>n+1));}
  return <><PageHead eyebrow="MONITORING / RULE ENGINE" title="Watchlists" description="Critères de surveillance configurables et expressions textuelles détectées lors des collectes autorisées."/>
    <div className="two-column"><Panel title="Listes de surveillance" kicker="WATCHLIST REGISTRY"><form className="inline-create" onSubmit={addWatchlist}><input aria-label="Nouvelle watchlist" value={newName} onChange={e=>setNewName(e.target.value)} minLength={2} maxLength={100} required placeholder="Nom de la watchlist"/><button className="btn btn-primary" type="submit" disabled={busy}><Icon name="plus" size={16}/> Créer</button></form><Failure text={error}/>
      {data.items.length?<div className="watchlist-list">{data.items.map(w=><div key={w.id} className={`watchlist-item ${selected?.id===w.id?'watchlist-selected':''}`}><button onClick={()=>{setSelected(w);setRuleSeq(n=>n+1);}}><span className="watchlist-logo"><Icon name="eye" size={18}/></span><span><strong>{w.name}</strong><small>{dateTime(w.created_at)}</small></span></button><button className="tiny-btn" onClick={()=>toggleWatchlist(w)}>{w.is_active?'Désactiver':'Activer'}</button></div>)}</div>:<Empty title={loading?'Chargement…':'Aucune watchlist'}/>}<Pager total={data.total} offset={offset} pageSize={limit} onChange={setOffset}/></Panel>
      <Panel title={selected?`Règles / ${selected.name}`:'Règles de surveillance'} kicker="KEYWORD RULES">
        {!selected?<Empty title="Sélectionnez une watchlist" text="Les règles de correspondance apparaîtront ici."/>:<><form className="rule-create" onSubmit={addRule}><label>Nouvelle expression<input value={phrase} onChange={e=>setPhrase(e.target.value)} minLength={2} maxLength={120} required placeholder="Expression exacte"/></label><label>Poids (1–30)<input type="number" min="1" max="30" value={weight} onChange={e=>setWeight(Number(e.target.value))}/></label><button className="btn btn-primary" disabled={busy} type="submit"><Icon name="plus" size={16}/> Ajouter</button></form><Failure text={rules.error}/>
        <div className="rules-list">{rules.data.items.length?rules.data.items.map(r=><div className="rule-row" key={r.id}><div><strong>{r.phrase}</strong><small>Poids : {r.weight} · <Status value={r.is_active}/></small></div><button className="tiny-btn" onClick={()=>toggleRule(r)}>{r.is_active?'Désactiver':'Activer'}</button></div>):<Empty title="Aucune règle" text="Ajoutez une expression pour commencer la surveillance."/>}</div></>}
      </Panel></div>
  </>;
}

export function Alerts({token,refresh,onNotice}:Shared){
  const [status,setStatus]=useState('OPEN');const [priority,setPriority]=useState('');const [offset,setOffset]=useState(0);const [seq,setSeq]=useState(0);
  const {data,loading,error}=useList<Alert>(token,'/api/v1/alerts'+query({limit,offset,status,priority}),refresh+seq);
  async function review(alert:Alert,next:'ACKNOWLEDGED'|'RESOLVED'){if(!window.confirm(`Passer cette alerte à ${next} ?`))return;
    await execute(()=>api.patch(token,`/api/v1/alerts/${alert.id}`,{status:next,reason:NOTE}),onNotice,'Alerte mise à jour.',()=>setSeq(n=>n+1));}
  return <><PageHead eyebrow="OPERATIONS / ALERT CENTER" title="Centre d'alertes" description="Signaux classés par priorité et état de traitement. Gestion et audit des décisions."/>
    <Panel title="Flux d'alertes" kicker="EVENT STREAM" action={<span className="counter">{data.total} alertes</span>}>
      <div className="filter-row"><Select value={status} change={v=>{setStatus(v);setOffset(0);}} label="Filtrer statut" options={[{value:'',label:'Tous les statuts'},{value:'OPEN',label:'Ouvertes'},{value:'ACKNOWLEDGED',label:'Acquittées'},{value:'RESOLVED',label:'Résolues'}]}/><Select value={priority} change={v=>{setPriority(v);setOffset(0);}} label="Filtrer priorité" options={[{value:'',label:'Toutes priorités'},{value:'HIGH',label:'HIGH'},{value:'MEDIUM',label:'MEDIUM'},{value:'LOW',label:'LOW'}]}/><span className="filter-hint"><Icon name="bell" size={15}/> Alertes internes à OIP</span></div>
      <Failure text={error}/><TableShell><thead><tr><th>Événement</th><th>Priorité</th><th>Source</th><th>Vérification</th><th>Score</th><th>Statut</th><th>Détecté</th><th>Action</th></tr></thead><tbody>
        {data.items.map(a=><tr key={a.id}><td><div className="cell-main"><strong>{a.event_type.replaceAll('_',' ')}</strong><span className="muted small">{a.signal_code}</span></div></td><td><Status value={a.priority}/></td><td><Mono value={a.source_id}/></td><td><Status value={a.verification_status}/></td><td><Score value={a.relevance_score}/></td><td><Status value={a.status}/></td><td><DateCell value={a.created_at}/></td><td><div className="row-actions">{a.status==='OPEN'&&<button className="tiny-btn" onClick={()=>review(a,'ACKNOWLEDGED')}>Acquitter</button>}{a.status!=='RESOLVED'&&<button className="tiny-btn tiny-approve" onClick={()=>review(a,'RESOLVED')}>Résoudre</button>}</div></td></tr>)}
        {!data.items.length&&tdEmpty(8,loading)}</tbody></TableShell><Pager total={data.total} offset={offset} pageSize={limit} onChange={setOffset}/>
    </Panel>
  </>;
}

export function Reports({token,refresh,onNotice}:Shared){
  const [offset,setOffset]=useState(0);const [seq,setSeq]=useState(0);const [showForm,setShowForm]=useState(false);
  const [from,setFrom]=useState(localDateInput(priorDays(30)));const [to,setTo]=useState(localDateInput(new Date()));const [maxRows,setMaxRows]=useState(100);
  const [source,setSource]=useState('');const [busy,setBusy]=useState(false);
  const {data,loading,error}=useList<Report>(token,'/api/v1/reports'+query({limit,offset}),refresh+seq);
  const sources=useList<Source>(token,'/api/v1/sources?limit=100',refresh);
  async function create(e:FormEvent){e.preventDefault();setBusy(true);
    try {const body={period_start:new Date(from).toISOString(),period_end:new Date(to).toISOString(),max_rows_per_type:maxRows,...(source?{source_id:source}:{})};
      await api.post(token,'/api/v1/reports',body);setShowForm(false);setOffset(0);setSeq(n=>n+1);onNotice('Rapport créé.');}
    catch(err){onNotice(readableError(err),'error');}finally{setBusy(false);}
  }
  async function exportReport(item:Report,format:'json'|'csv') {await execute(()=>downloadExport(token,`/api/v1/reports/${item.id}/export?format=${format}`,`oip-report-${item.id}.${format}`),onNotice,'Export téléchargé.',()=>{});}
  return <><PageHead eyebrow="INTELLIGENCE / EXPORTS" title="Rapports CTI" description="Produisez des snapshots documentaires figés au format JSON ou CSV." actions={<button className="btn btn-primary" onClick={()=>setShowForm(true)}><Icon name="plus"/> Générer un rapport</button>}/>
    <Panel title="Rapports archivés" kicker="SNAPSHOT HISTORY" action={<span className="counter">{data.total} rapports</span>}><Failure text={error}/>
      <TableShell><thead><tr><th>Identifiant</th><th>Source</th><th>Début de période</th><th>Fin de période</th><th>Créé le</th><th>Exports</th></tr></thead><tbody>{data.items.map(r=><tr key={r.id}><td><div className="cell-main"><Mono value={r.id}/><span className="muted small">Snapshot immuable</span></div></td><td>{r.source_id?<Mono value={r.source_id}/>:<span className="category-tag">Toutes sources</span>}</td><td><DateCell value={r.period_start}/></td><td><DateCell value={r.period_end}/></td><td><DateCell value={r.created_at}/></td><td><div className="row-actions"><button className="tiny-btn" onClick={()=>exportReport(r,'json')}><Icon name="download" size={14}/> JSON</button><button className="tiny-btn" onClick={()=>exportReport(r,'csv')}><Icon name="download" size={14}/> CSV</button></div></td></tr>)}{!data.items.length&&tdEmpty(6,loading)}</tbody></TableShell>
      <Pager total={data.total} offset={offset} pageSize={limit} onChange={setOffset}/>
    </Panel>
    <div className="notice-strip"><Icon name="file"/><p>Les rapports contiennent uniquement des métadonnées autorisées. Ils distinguent les observations documentaires des allégations non vérifiées.</p></div>
    {showForm&&<div className="modal-shade" onMouseDown={e=>{if(e.target===e.currentTarget)setShowForm(false);}}><section className="modal" role="dialog" aria-modal="true" aria-label="Créer un rapport"><div className="modal-head"><div><p className="eyebrow">REPORT GENERATOR</p><h2>Nouveau rapport</h2></div><button className="icon-button" aria-label="Fermer" onClick={()=>setShowForm(false)}><Icon name="x"/></button></div>
      <form className="form-grid" onSubmit={create}><label>Date de début<input type="datetime-local" required value={from} onChange={e=>setFrom(e.target.value)}/></label><label>Date de fin<input type="datetime-local" required value={to} onChange={e=>setTo(e.target.value)}/></label><label>Source<select value={source} onChange={e=>setSource(e.target.value)}><option value="">Toutes les sources</option>{sources.data.items.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</select></label><label>Maximum de lignes / type<input type="number" min={1} max={200} value={maxRows} onChange={e=>setMaxRows(Number(e.target.value))}/></label><div className="form-actions"><button className="btn btn-secondary" type="button" onClick={()=>setShowForm(false)}>Annuler</button><button className="btn btn-primary" disabled={busy} type="submit">{busy?'Génération…':'Créer le rapport'}</button></div></form></section></div>}
  </>;
}
