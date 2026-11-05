import { useEffect, useState } from 'react';
import { publicGet, totalLabels } from '../lib/publicApi';
import type { PublicActivity, PublishedReport } from '../lib/publicApi';
import type { Page } from '../lib/types';
import { DateCell, Empty, Icon, PageHead, Pager, Panel, Status } from './ui';

const pageSize=20;
function usePublicPage<T>(path:string,refresh:number){
  const [data,setData]=useState<Page<T>>({items:[],total:0,limit:pageSize,offset:0});
  const [loading,setLoading]=useState(true);const [error,setError]=useState('');
  useEffect(()=>{const abort=new AbortController();setLoading(true);setError('');
    publicGet<Page<T>>(path,abort.signal).then(value=>{if(!abort.signal.aborted)setData(value);})
      .catch(()=>{if(!abort.signal.aborted){setData({items:[],total:0,limit:pageSize,offset:0});setError('La vitrine est temporairement indisponible.');}})
      .finally(()=>{if(!abort.signal.aborted)setLoading(false);});
    return ()=>abort.abort();
  },[path,refresh]);
  return {data,loading,error};
}

export function VisitorView({onAdmin}:{onAdmin:()=>void}){
  const [tab,setTab]=useState<'activity'|'reports'>('activity');
  const [offset,setOffset]=useState(0);const [reportOffset,setReportOffset]=useState(0);
  const [refresh,setRefresh]=useState(0);
  const activity=usePublicPage<PublicActivity>(`/api/public/v1/activity?limit=${pageSize}&offset=${offset}`,refresh);
  const reports=usePublicPage<PublishedReport>(`/api/public/v1/reports?limit=${pageSize}&offset=${reportOffset}`,refresh);
  return <div className="shell visitor-shell"><aside className="sidebar">
    <div className="brand"><span className="brand-mark"><Icon name="radar" size={24}/></span><span><strong>OIP<span className="accent">.</span></strong><small>VITRINE PUBLIQUE</small></span></div>
    <nav aria-label="Navigation visiteur"><div className="nav-group">VEILLE DOCUMENTAIRE</div>
      <button className={`nav-link ${tab==='activity'?'nav-link-active':''}`} aria-current={tab==='activity'?'page':undefined} onClick={()=>setTab('activity')}><Icon name="activity"/>Dernières veilles</button>
      <button className={`nav-link ${tab==='reports'?'nav-link-active':''}`} aria-current={tab==='reports'?'page':undefined} onClick={()=>setTab('reports')}><Icon name="file"/>Rapports publics</button>
    </nav><div className="sidebar-bottom"><div className="secure-card"><Icon name="eye"/><strong>Accès visiteur</strong><p>Consultation des seules informations publiques.</p></div><button className="nav-link" onClick={onAdmin}><Icon name="lock"/>Connexion opérateur</button></div>
  </aside><div className="main-area"><div className="topbar"><span className="topbar-env">VITRINE · LECTURE SEULE</span><div className="topbar-right"><button className="icon-button" aria-label="Actualiser la vitrine" onClick={()=>setRefresh(n=>n+1)}><Icon name="refresh"/></button><button className="btn btn-secondary" onClick={onAdmin}>Connexion opérateur</button></div></div>
    <main className="content">
      {tab==='activity'?<><PageHead eyebrow="OIP / ACCÈS VISITEUR" title="Dernières veilles" description="Collectes terminées : dates, sources et volumes documentaires, sans adresse Onion."/>
        <Panel title="Activité récente" kicker="MÉTADONNÉES PUBLIQUES">
          {activity.error?<p role="alert" className="inline-error">{activity.error}</p>:activity.loading?<p role="status" className="visitor-loading">Chargement des veilles…</p>:activity.data.items.length?<div className="table-scroller"><table><thead><tr><th>Date de collecte</th><th>Source</th><th>Statut</th><th>Octets reçus</th><th>Caractères extraits</th></tr></thead><tbody>{activity.data.items.map((item,i)=><tr key={`${item.date}-${i}`}><td><DateCell value={item.date}/></td><td>{item.source_name}</td><td><Status value={item.status}/></td><td>{item.response_bytes===null?'—':item.response_bytes.toLocaleString('fr-FR')}</td><td>{item.text_characters===null?'—':item.text_characters.toLocaleString('fr-FR')}</td></tr>)}</tbody></table></div>:<Empty title="Aucune veille publique" text="Les collectes terminées apparaîtront ici lorsqu’elles seront disponibles."/>}
          <Pager total={activity.data.total} offset={offset} pageSize={pageSize} onChange={setOffset}/>
        </Panel></>:<><PageHead eyebrow="OIP / PUBLICATIONS" title="Rapports publics" description="Versions agrégées publiées explicitement par l’administrateur."/>
        {reports.error?<p role="alert" className="inline-error">{reports.error}</p>:reports.loading?<p role="status">Chargement des rapports…</p>:reports.data.items.length?reports.data.items.map(report=><Panel key={report.id} title="Rapport de veille" kicker="PUBLICATION ADMINISTRATEUR"><div className="public-report-period"><span>Du <DateCell value={report.content.period_start}/> au <DateCell value={report.content.period_end}/></span><span>Publié le <DateCell value={report.published_at}/></span></div>
          <dl className="public-totals">{Object.entries(totalLabels).map(([key,label])=><div key={key}><dt>{label}</dt><dd>{report.content.totals[key as keyof typeof totalLabels].toLocaleString('fr-FR')}</dd></div>)}</dl><p className="muted small public-disclaimer">{report.content.disclaimer}</p></Panel>):<Empty title="Aucun rapport public" text="Les rapports internes restent privés tant que l’administrateur ne les publie pas."/>}
        <Pager total={reports.data.total} offset={reportOffset} pageSize={pageSize} onChange={setReportOffset}/></>}
      <div className="notice-strip"><Icon name="shield"/><p>Une mention, un volume ou une alerte documentaire ne prouve ni compromission ni activité illicite.</p></div>
    </main><footer className="page-footer"><span>OIP · VEILLE DOCUMENTAIRE CONTRÔLÉE</span><span>Vitrine publique · aucune fonction de collecte</span></footer>
  </div></div>;
}
