/** M6-B: manual, metadata-only analyst cases with explicit version checks. */
import { useEffect, useState } from 'react';
import { api, ApiError } from '../lib/api';
import type { Alert, AnalystCase, AnalystCaseEvent, CaseAction, CaseNote, CaseNoteCode, CasePriority, CaseNotificationPreview, Page } from '../lib/types';
import { readableError } from '../lib/util';
import { canCaseTransition } from '../lib/caseWorkflow';
import { DateCell, Empty, Mono, PageHead, Pager, Panel, Status } from './ui';

type Props = {token:string;refresh:number;onNotice:(text:string,kind?:'success'|'error')=>void};
const pageSize=20;

export function CaseDesk({token,refresh,onNotice}:Props) {
  const [cases,setCases]=useState<Page<AnalystCase>>({total:0,offset:0,limit:pageSize,items:[]});
  const [alerts,setAlerts]=useState<Alert[]>([]);
  const [assignees,setAssignees]=useState<{username:string;role:string}[]>([]);
  const [offset,setOffset]=useState(0);const [status,setStatus]=useState('');const [seq,setSeq]=useState(0);
  const [alertId,setAlertId]=useState('');const [selected,setSelected]=useState<AnalystCase|null>(null);
  const [history,setHistory]=useState<AnalystCaseEvent[]>([]);
  const [notes,setNotes]=useState<CaseNote[]>([]);
  const [priority,setPriority]=useState<CasePriority>('UNASSESSED');
  const [escalationReason,setEscalationReason]=useState('REVIEW_REQUIRED');
  const [noteCode,setNoteCode]=useState<CaseNoteCode>('ANALYST_CONTEXT');
  const [noteBody,setNoteBody]=useState('');
  const [preview,setPreview]=useState<CaseNotificationPreview|null>(null);
  const [assignee,setAssignee]=useState('');const [closureCode,setClosureCode]=useState('DOCUMENTED');
  const [busy,setBusy]=useState(false);const [loading,setLoading]=useState(true);const [error,setError]=useState('');

  useEffect(()=>{let live=true;setLoading(true);setError('');
    api.get<Page<AnalystCase>>(token,`/api/v1/cases?limit=${pageSize}&offset=${offset}${status?'&status='+status:''}`)
      .then(r=>{if(live)setCases(r)}).catch(e=>{if(live)setError(readableError(e))})
      .finally(()=>{if(live)setLoading(false)});
    return ()=>{live=false};
  },[token,refresh,seq,offset,status]);
  useEffect(()=>{let live=true;
    Promise.all([api.get<Page<Alert>>(token,'/api/v1/alerts?limit=100'),
      api.get<{username:string;role:string}[]>(token,'/api/v1/cases/assignees')])
      .then(([a,users])=>{if(live){setAlerts(a.items);setAssignees(users)}})
      .catch(e=>{if(live)setError(readableError(e))});
    return ()=>{live=false};
  },[token,refresh,seq]);
  useEffect(()=>{let live=true;
    if (!selected){setHistory([]);setNotes([]);setPreview(null);return ()=>{live=false};}
    Promise.all([
      api.get<Page<AnalystCaseEvent>>(token,`/api/v1/cases/${selected.id}/events?limit=100`),
      api.get<Page<CaseNote>>(token,`/api/v1/cases/${selected.id}/notes?limit=100`),
      api.get<CaseNotificationPreview>(token,`/api/v1/cases/${selected.id}/notification-preview`),
    ]).then(([events,comments,notice])=>{if(live){setHistory(events.items);setNotes(comments.items);setPreview(notice)}})
      .catch(e=>{if(live)setError(readableError(e))});
    return ()=>{live=false};
  },[token,selected]);
  async function createCase(){if(!alertId)return;setBusy(true);setError('');
    try{const fresh=await api.post<AnalystCase>(token,'/api/v1/cases',{alert_id:alertId});
      setSeq(n=>n+1);setSelected(fresh);setAlertId('');onNotice('Dossier créé.');}
    catch(e){onNotice(readableError(e),'error')}finally{setBusy(false)}
  }
  async function action(row:AnalystCase, name:CaseAction){
    if(!window.confirm(`Confirmer ${name} pour le dossier ${row.id.slice(0,8)} ?`))return;
    setBusy(true);setError('');
    const payload:{action:CaseAction;expected_version:number;assignee_username?:string;closure_code?:string;priority?:CasePriority;escalation_reason?:string}={action:name,expected_version:row.version};
    if(name==='ASSIGN')payload.assignee_username=assignee;
    if(name==='CLOSE')payload.closure_code=closureCode;
    if(name==='SET_PRIORITY')payload.priority=priority;
    if(name==='ESCALATE')payload.escalation_reason=escalationReason;
    try{const updated=await api.patch<AnalystCase>(token,`/api/v1/cases/${row.id}`,payload);
      setSelected(updated);setSeq(n=>n+1);onNotice('Dossier mis à jour.');}
    catch(e){if(e instanceof ApiError&&e.status===409){onNotice('Conflit de version : actualisez le dossier.', 'error');setSeq(n=>n+1)}
      else onNotice(readableError(e),'error')}
    finally{setBusy(false)}
  }
  async function addNote(){if(!selected||!noteBody.trim())return;
    setBusy(true);
    try {
      await api.post<CaseNote>(token,`/api/v1/cases/${selected.id}/notes`,
        {expected_version:selected.version,note_code:noteCode,body:noteBody});
      setNoteBody('');const updated=await api.get<AnalystCase>(token,`/api/v1/cases/${selected.id}`);
      setSelected(updated);setSeq(n=>n+1);onNotice('Annotation enregistrée.');
    } catch(e) {onNotice(e instanceof ApiError&&e.status===409?'Conflit de version : actualisez le dossier.':readableError(e),'error');}
    finally{setBusy(false)}
  }
  async function open(row:AnalystCase){setSelected(row);setAssignee(row.assignee_username||'');setPriority(row.priority);}
  const label=(id:string)=>alerts.find(a=>a.id===id)?.signal_code || id.slice(0,8);
  return <><PageHead eyebrow="INVESTIGATION / M6-B" title="Dossiers d’analyse"
    description="Suivi humain des alertes : priorité, responsable, annotations courtes et décisions tracées. Aucun signal n’est une preuve d’incident."/>
    <Panel title="Ouvrir un dossier" kicker="ALERTE EXISTANTE / OUVERTURE MANUELLE">
      <div className="filter-row"><label className="select-wrap"><span className="sr-only">Alerte à suivre</span>
        <select aria-label="Alerte à suivre" value={alertId} onChange={e=>setAlertId(e.target.value)}>
          <option value="">Sélectionner une alerte (100 plus récentes)</option>
          {alerts.map(a=><option key={a.id} value={a.id}>{a.signal_code} · {a.id.slice(0,8)} · {a.priority}</option>)}
        </select></label><button className="btn btn-primary" onClick={()=>void createCase()} disabled={!alertId||busy}>Créer le dossier</button></div>
      <p className="page-footnote">Un seul dossier par alerte. Une alerte déjà associée produit un refus sans modification.</p>
    </Panel>
    <Panel title="Dossiers" kicker="TRIAGE / SUIVI" action={<span className="counter">{cases.total} dossiers</span>}>
      <div className="filter-row"><label className="select-wrap"><span className="sr-only">Statut des dossiers</span>
        <select aria-label="Statut des dossiers" value={status} onChange={e=>{setStatus(e.target.value);setOffset(0)}}>
          <option value="">Tous les statuts</option>{['OPEN','IN_REVIEW','ESCALATED','CLOSED'].map(s=><option key={s} value={s}>{s}</option>)}
        </select></label></div>
      {error&&<div role="alert" className="inline-error">{error}</div>}
      <div className="table-scroller"><table><thead><tr><th>Alerte</th><th>Statut</th><th>Priorité</th><th>Responsable</th><th>Version</th><th>Actualisé</th><th>Action</th></tr></thead>
        <tbody>{cases.items.map(row=><tr key={row.id}><td>{label(row.alert_id)} <Mono value={row.alert_id}/></td>
          <td><Status value={row.status}/></td><td>{row.priority}</td><td>{row.assignee_username||'Non assigné'}</td><td>{row.version}</td>
          <td><DateCell value={row.updated_at}/></td><td><button className="tiny-btn" onClick={()=>void open(row)}>Examiner</button></td></tr>)}
          {!cases.items.length&&<tr><td colSpan={7}><Empty title={loading?'Chargement…':'Aucun dossier'} text="Sélectionnez une alerte pour créer un dossier."/></td></tr>}</tbody></table></div>
      <Pager total={cases.total} offset={offset} pageSize={pageSize} onChange={setOffset}/>
    </Panel>
    {selected&&<Panel title={`Dossier ${selected.id.slice(0,8)}`} kicker="DÉCISIONS / HISTORIQUE" action={<button className="tiny-btn" onClick={()=>setSelected(null)}>Fermer</button>}>
      <p>Statut : <Status value={selected.status}/> · Priorité {selected.priority} · Version {selected.version} · Alerte <Mono value={selected.alert_id}/></p>
      <div className="filter-row"><label className="select-wrap"><span className="sr-only">Assigner à</span>
        <select aria-label="Assigner à" value={assignee} onChange={e=>setAssignee(e.target.value)}>
          <option value="">Choisir un analyste</option>{assignees.map(a=><option key={a.username} value={a.username}>{a.username} ({a.role})</option>)}
        </select></label>
        <button className="tiny-btn" disabled={busy||!assignee||!canCaseTransition(selected.status,'ASSIGN')} onClick={()=>void action(selected,'ASSIGN')}>Assigner</button>
        <button className="tiny-btn" disabled={busy||!selected.assignee_id||!canCaseTransition(selected.status,'UNASSIGN')} onClick={()=>void action(selected,'UNASSIGN')}>Désassigner</button>
        {canCaseTransition(selected.status,'START_REVIEW')&&<button className="tiny-btn" disabled={busy} onClick={()=>void action(selected,'START_REVIEW')}>Démarrer revue</button>}
        {canCaseTransition(selected.status,'ESCALATE')&&<><label className="select-wrap"><span className="sr-only">Motif d’escalade</span><select aria-label="Motif d’escalade" value={escalationReason} onChange={e=>setEscalationReason(e.target.value)}>{['REVIEW_REQUIRED','TIME_SENSITIVE','MULTI_SOURCE','OTHER'].map(x=><option key={x} value={x}>{x}</option>)}</select></label><button className="tiny-btn" disabled={busy} onClick={()=>void action(selected,'ESCALATE')}>Escalader</button></>}
        {canCaseTransition(selected.status,'RETURN_REVIEW')&&<button className="tiny-btn" disabled={busy} onClick={()=>void action(selected,'RETURN_REVIEW')}>Reprendre revue</button>}
        {selected.status!=='CLOSED'&&<><label className="select-wrap"><span className="sr-only">Priorité du dossier</span><select aria-label="Priorité du dossier" value={priority} onChange={e=>setPriority(e.target.value as CasePriority)}>{['UNASSESSED','LOW','MEDIUM','HIGH','CRITICAL'].map(x=><option key={x} value={x}>{x}</option>)}</select></label><button className="tiny-btn" disabled={busy||priority===selected.priority} onClick={()=>void action(selected,'SET_PRIORITY')}>Changer priorité</button></>}
        {canCaseTransition(selected.status,'CLOSE')&&<><label className="select-wrap"><span className="sr-only">Motif de clôture</span>
          <select aria-label="Motif de clôture" value={closureCode} onChange={e=>setClosureCode(e.target.value)}>
            {['DOCUMENTED','NOT_RELEVANT','DUPLICATE'].map(c=><option key={c} value={c}>{c}</option>)}</select></label>
          <button className="tiny-btn tiny-approve" disabled={busy} onClick={()=>void action(selected,'CLOSE')}>Clore</button></>}
      </div>
      <div className="table-scroller"><table><thead><tr><th>Version</th><th>Opérateur</th><th>Action</th><th>Statut</th><th>Responsable visé</th><th>Motif codifié</th><th>Date</th></tr></thead>
        <tbody>{history.map(e=><tr key={e.id}><td>{e.version}</td><td>{e.actor}</td><td>{e.action}</td><td><Status value={e.to_status}/></td>
          <td>{e.assignee_username||'—'}</td><td>{e.reason_code||'—'}</td><td><DateCell value={e.created_at}/></td></tr>)}
          {!history.length&&<tr><td colSpan={7}>Aucun événement.</td></tr>}</tbody></table></div>
      <h3>Annotations internes contrôlées</h3>
      <p className="page-footnote">300 caractères maximum, pas de lien, données personnelles, identifiants ou extrait brut. Réservé aux analystes autorisés ; les notes ne sont pas copiées dans l’audit.</p>
      {selected.status!=='CLOSED'&&<div className="filter-row"><label className="select-wrap"><span className="sr-only">Catégorie d’annotation</span><select aria-label="Catégorie d’annotation" value={noteCode} onChange={e=>setNoteCode(e.target.value as CaseNoteCode)}>{['ANALYST_CONTEXT','FOLLOW_UP','FALSE_POSITIVE_CHECK','ESCALATION_CONTEXT'].map(x=><option key={x} value={x}>{x}</option>)}</select></label>
      <input aria-label="Annotation interne" value={noteBody} onChange={e=>setNoteBody(e.target.value)} maxLength={300} placeholder="Observation synthétique (8 à 300 caractères)"/>
      <button className="tiny-btn" disabled={busy||noteBody.trim().length<8} onClick={()=>void addNote()}>Enregistrer note</button></div>}
      <div className="table-scroller"><table><thead><tr><th>Version</th><th>Catégorie</th><th>Analyste</th><th>Annotation</th><th>Date</th></tr></thead><tbody>{notes.map(n=><tr key={n.id}><td>{n.case_version}</td><td>{n.note_code}</td><td>{n.actor}</td><td>{n.body}</td><td><DateCell value={n.created_at}/></td></tr>)}{!notes.length&&<tr><td colSpan={5}>Aucune annotation.</td></tr>}</tbody></table></div>
      <h3>Notifications — aperçu seulement</h3>
      <p className="page-footnote">{preview?`Envoi : ${preview.delivery} · Modèle ${preview.template} · Contenu ${preview.contents} · ${preview.destinations.length} destination(s).`: 'Aucun canal actif.'} Aucune transmission externe ni webhook n’est implémenté.</p>
      <p className="page-footnote">Une clôture de dossier ne modifie pas le statut de l’alerte.</p>
    </Panel>}
  </>;
}
