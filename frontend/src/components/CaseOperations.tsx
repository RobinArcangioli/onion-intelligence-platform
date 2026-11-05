/** M6-C local-only operational summary and reviewed notification drafts. */
import {useEffect, useState} from 'react';
import {api} from '../lib/api';
import {readableError} from '../lib/util';
import type {AnalystCase, CaseNotificationDraft, CaseNotificationPolicy, CaseOperationsSummary, CasePriority, CaseStatus, Page} from '../lib/types';
import {Empty, PageHead, Panel, Status} from './ui';

type Props={token:string;refresh:number;role:string;onNotice:(message:string,kind?:'success'|'error')=>void};
const statuses:CaseStatus[]=['OPEN','IN_REVIEW','ESCALATED','CLOSED'];
const priorities:CasePriority[]=['UNASSESSED','LOW','MEDIUM','HIGH','CRITICAL'];
const root='/api/v1/case-operations';

export function CaseOperations({token,refresh,role,onNotice}:Props){
  const [summary,setSummary]=useState<CaseOperationsSummary|null>(null);
  const [policies,setPolicies]=useState<CaseNotificationPolicy[]>([]);
  const [drafts,setDrafts]=useState<Page<CaseNotificationDraft>>({total:0,items:[],limit:20,offset:0});
  const [cases,setCases]=useState<AnalystCase[]>([]);
  const [code,setCode]=useState('CASE_ESCALATION_V1');
  const [targetStatus,setTargetStatus]=useState<CaseStatus>('ESCALATED');
  const [minimumPriority,setMinimumPriority]=useState<CasePriority>('HIGH');
  const [selectedCase,setSelectedCase]=useState('');const [selectedPolicy,setSelectedPolicy]=useState('');
  const [busy,setBusy]=useState(false);const [error,setError]=useState('');const [seq,setSeq]=useState(0);
  useEffect(()=>{let live=true;setError('');
    Promise.all([
      api.get<CaseOperationsSummary>(token,`${root}/summary`),
      api.get<CaseNotificationPolicy[]>(token,`${root}/policies`),
      api.get<Page<CaseNotificationDraft>>(token,`${root}/drafts?limit=20`),
      api.get<Page<AnalystCase>>(token,'/api/v1/cases?limit=100'),
    ]).then(([s,p,d,c])=>{if(live){setSummary(s);setPolicies(p);setDrafts(d);setCases(c.items);}})
      .catch(e=>{if(live)setError(readableError(e))});
    return()=>{live=false};
  },[token,refresh,seq]);
  async function createPolicy(){setBusy(true);
    try{await api.post(token,`${root}/policies`,{code,target_status:targetStatus,minimum_priority:minimumPriority});
      onNotice('Politique créée, désactivée en attente d’approbation.');setSeq(n=>n+1);}
    catch(e){onNotice(readableError(e),'error')}finally{setBusy(false)}
  }
  async function setPolicy(p:CaseNotificationPolicy,approved:boolean,enabled:boolean){
    if(!window.confirm(enabled?'Autoriser la préparation locale de notifications ? Aucun envoi ne sera effectué.':'Désactiver cette politique ?'))return;
    setBusy(true);
    try{await api.patch(token,`${root}/policies/${p.id}`,{expected_version:p.version,approved,enabled});
      onNotice('Politique mise à jour (aucun transport externe).');setSeq(n=>n+1);}
    catch(e){onNotice(readableError(e),'error')}finally{setBusy(false)}
  }
  async function prepare(){const c=cases.find(x=>x.id===selectedCase);if(!c||!selectedPolicy)return;
    if(!window.confirm(`Préparer uniquement une notification interne pour le dossier ${c.id.slice(0,8)} ?`))return;
    setBusy(true);
    try{await api.post(token,`${root}/drafts`,{case_id:c.id,policy_id:selectedPolicy,expected_case_version:c.version});
      onNotice('Notification préparée localement. Aucun message envoyé.');setSeq(n=>n+1);}
    catch(e){onNotice(readableError(e),'error')}finally{setBusy(false)}
  }
  return <><PageHead eyebrow="EXPLOITATION / M6-C" title="Opérations analystes"
    description="Rapport agrégé et notifications préparées localement. Aucun SMTP, webhook ni envoi automatique."/>
    {error&&<div className="inline-error" role="alert">{error}</div>}
    <Panel title="Rapport opérationnel" kicker="STATISTIQUES AGRÉGÉES">
      {summary?<><p><strong>{summary.total_cases}</strong> dossiers · {summary.open_unassigned} ouverts non assignés · {summary.notification_drafts} notifications préparées · <strong>0 envoyée</strong></p>
        <div className="table-scroller"><table><thead><tr><th>Statut</th><th>Nombre</th><th>Priorité</th><th>Nombre</th></tr></thead><tbody>
          {statuses.map((s,i)=><tr key={s}><td><Status value={s}/></td><td>{summary.by_status[s]}</td><td>{priorities[i]}</td><td>{summary.by_priority[priorities[i]]}</td></tr>)}
          <tr><td>—</td><td>—</td><td>{priorities[4]}</td><td>{summary.by_priority.CRITICAL}</td></tr>
        </tbody></table></div></>:<Empty title="Chargement des statistiques" text="Les statistiques ne contiennent aucune annotation."/>}
      <p className="page-footnote">Rapport agrégé, sans texte de collecte, annotation, adresse externe ou contenu d’alerte.</p>
    </Panel>
    {role==='ADMIN'&&<Panel title="Créer une politique" kicker="ADMIN / DÉSACTIVÉE PAR DÉFAUT">
      <div className="filter-row"><input aria-label="Code politique" value={code} maxLength={32} onChange={e=>setCode(e.target.value.toUpperCase())} placeholder="CASE_ESCALATION_V1"/>
        <label className="select-wrap"><span className="sr-only">Statut ciblé</span><select aria-label="Statut ciblé" value={targetStatus} onChange={e=>setTargetStatus(e.target.value as CaseStatus)}>{statuses.map(s=><option key={s}>{s}</option>)}</select></label>
        <label className="select-wrap"><span className="sr-only">Priorité minimale</span><select aria-label="Priorité minimale" value={minimumPriority} onChange={e=>setMinimumPriority(e.target.value as CasePriority)}>{priorities.map(s=><option key={s}>{s}</option>)}</select></label>
        <button className="tiny-btn" disabled={busy||!(/^[A-Z][A-Z0-9_]{2,31}$/.test(code))} onClick={()=>void createPolicy()}>Créer désactivée</button>
      </div>
    </Panel>}
    <Panel title="Politiques locales" kicker="APPROBATION ADMIN / AUCUN CANAL DE SORTIE">
      <div className="table-scroller"><table><thead><tr><th>Code</th><th>Statut ciblé</th><th>Priorité minimale</th><th>Approbation</th><th>Transport</th><th>Action</th></tr></thead><tbody>{policies.map(p=><tr key={p.id}>
        <td>{p.code}</td><td>{p.target_status}</td><td>{p.minimum_priority}</td><td>{p.enabled?'Préparation autorisée':'Désactivée'}</td><td>{p.transport}</td>
        <td>{role==='ADMIN'?<button className="tiny-btn" disabled={busy} onClick={()=>void setPolicy(p,!p.enabled,!p.enabled)}>{p.enabled?'Suspendre':'Approuver'}</button>:'Lecture seule'}</td>
      </tr>)}{!policies.length&&<tr><td colSpan={6}>Aucune politique : toutes les notifications restent désactivées.</td></tr>}</tbody></table></div>
    </Panel>
    <Panel title="Préparer une notification" kicker="MANUEL / SANS ENVOI">
      <div className="filter-row"><label className="select-wrap"><span className="sr-only">Dossier</span><select aria-label="Dossier" value={selectedCase} onChange={e=>setSelectedCase(e.target.value)}><option value="">Choisir un dossier (100 derniers)</option>{cases.map(c=><option key={c.id} value={c.id}>{c.id.slice(0,8)} · {c.status} · {c.priority} · v{c.version}</option>)}</select></label>
        <label className="select-wrap"><span className="sr-only">Politique approuvée</span><select aria-label="Politique approuvée" value={selectedPolicy} onChange={e=>setSelectedPolicy(e.target.value)}><option value="">Politique approuvée</option>{policies.filter(p=>p.approved&&p.enabled).map(p=><option key={p.id} value={p.id}>{p.code}</option>)}</select></label>
        <button className="tiny-btn" disabled={busy||!selectedCase||!selectedPolicy} onClick={()=>void prepare()}>Préparer sans envoyer</button></div>
    </Panel>
    <Panel title="Registre des notifications préparées" kicker="NOT_SENT / LOCAL ONLY" action={<span className="counter">{drafts.total} éléments</span>}>
      <div className="table-scroller"><table><thead><tr><th>Dossier</th><th>Politique</th><th>Version</th><th>État</th><th>Créateur</th></tr></thead><tbody>{drafts.items.map(d=><tr key={d.id}><td>{d.case_id.slice(0,8)}</td><td>{d.payload.policy_code}</td><td>{d.case_version}</td><td><strong>{d.delivery_status}</strong></td><td>{d.created_by}</td></tr>)}
        {!drafts.items.length&&<tr><td colSpan={5}>Aucune notification préparée.</td></tr>}</tbody></table></div>
      <p className="page-footnote">Aucune destination n’est enregistrée. Ces éléments ne seront jamais envoyés par cette version d’OIP.</p>
    </Panel>
  </>;
}
