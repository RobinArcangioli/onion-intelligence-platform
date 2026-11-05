import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { api, ApiError } from '../lib/api';

type Schedule = {source_id:string;enabled:boolean;interval_minutes:number;daily_budget:number;window_start_hour:number;window_end_hour:number;expires_at:string;approval_reference:string;next_run_at:string};
type Decision = {id:string;decision:string;created_at:string;job_id:string|null};
const utcDate = (daysAhead:number) => new Date(Date.now()+daysAhead*86400000).toISOString().slice(0,10);

export function ScheduleEditor({token,sourceId,sourceName,onClose,onNotice}: {
  token:string;sourceId:string;sourceName:string;onClose:()=>void;
  onNotice:(text:string,kind?:'success'|'error')=>void;
}) {
  const [enabled,setEnabled] = useState(false);
  const [interval,setInterval] = useState(60);
  const [budget,setBudget] = useState(1);
  const [start,setStart] = useState(0);
  const [end,setEnd] = useState(24);
  const [expiry,setExpiry] = useState(utcDate(14));
  const [reference,setReference] = useState('');
  const [reason,setReason] = useState('');
  const [loaded,setLoaded] = useState(false);
  const [saving,setSaving] = useState(false);
  const [next,setNext] = useState('');
  const [decisions,setDecisions] = useState<Decision[]>([]);
  const [error,setError] = useState('');
  useEffect(()=>{let live=true;
    Promise.all([
      api.get<Schedule>(token,`/api/v1/schedules/${sourceId}`).catch(e=>{if(e instanceof ApiError && e.status===404)return null;throw e;}),
      api.get<Decision[]>(token,`/api/v1/schedules/${sourceId}/decisions?limit=10`),
    ]).then(([schedule,history])=>{if(!live)return;
      setDecisions(history);
      if(schedule){setEnabled(schedule.enabled);setInterval(schedule.interval_minutes);setBudget(schedule.daily_budget);
        setStart(schedule.window_start_hour);setEnd(schedule.window_end_hour);
        setExpiry(schedule.expires_at.slice(0,10));setReference(schedule.approval_reference);setNext(schedule.next_run_at);}
    }).catch(e=>{if(live)setError(e instanceof Error?e.message:'Erreur de chargement');})
      .finally(()=>{if(live)setLoaded(true);});
    return ()=>{live=false;};
  },[token,sourceId]);
  async function save(e:FormEvent){e.preventDefault();setSaving(true);setError('');
    try{
      const result=await api.put<Schedule>(token,`/api/v1/schedules/${sourceId}`,{
        enabled,interval_minutes:interval,daily_budget:budget,window_start_hour:start,window_end_hour:end,
        expires_at:`${expiry}T23:59:59Z`,approval_reference:reference,reason,
      });
      setNext(result.next_run_at);onNotice('Planification enregistrée. Le scheduler global reste désactivé sauf activation séparée.');onClose();
    }catch(e){setError(e instanceof Error?e.message:'Erreur de sauvegarde');onNotice('Échec de configuration','error');}
    finally{setSaving(false);}
  }
  async function pause(){setSaving(true);setError('');
    try{await api.post(token,`/api/v1/schedules/${sourceId}/pause`,{reason:reason.trim()});onNotice('Planification suspendue.');onClose();}
    catch(e){setError(e instanceof Error?e.message:'Erreur de suspension');}
    finally{setSaving(false);}
  }
  return <div className="modal-shade" onMouseDown={e=>{if(e.currentTarget===e.target)onClose();}}>
    <section className="modal modal-wide" role="dialog" aria-modal="true" aria-label="Planification gouvernée">
      <div className="modal-head"><div><p className="eyebrow">M3 / SCHEDULER OPT-IN</p><h2>Planification · {sourceName}</h2></div><button className="icon-button" aria-label="Fermer" onClick={onClose}>×</button></div>
      <p className="page-footnote">Le scheduler est désactivé globalement par défaut. Activer cette configuration ne démarre ni Tor ni une collecte. Fuseau horaire : UTC. Approbation et durée limitées obligatoires.</p>
      {!loaded?<p>Chargement…</p>:<form className="form-grid" onSubmit={save}>
        <label className="check-label"><input type="checkbox" checked={enabled} onChange={e=>setEnabled(e.target.checked)}/><span>Autoriser explicitement la surveillance périodique de cette source</span></label>
        <label>Intervalle minimal (minutes, ≥ 60)<input type="number" min={60} max={10080} required value={interval} onChange={e=>setInterval(Number(e.target.value))}/></label>
        <label>Budget de jobs quotidiens (1–24)<input type="number" min={1} max={24} required value={budget} onChange={e=>setBudget(Number(e.target.value))}/></label>
        <label>Fenêtre UTC : début (0–23)<input type="number" min={0} max={23} required value={start} onChange={e=>setStart(Number(e.target.value))}/></label>
        <label>Fenêtre UTC : fin exclusive (1–24)<input type="number" min={1} max={24} required value={end} onChange={e=>setEnd(Number(e.target.value))}/></label>
        <label>Expiration de l'autorisation (UTC)<input type="date" required value={expiry} onChange={e=>setExpiry(e.target.value)}/></label>
        <label>Référence d'autorisation<input required minLength={10} maxLength={500} value={reference} onChange={e=>setReference(e.target.value)}/></label>
        <label>Justification de la décision<input required minLength={10} maxLength={500} value={reason} onChange={e=>setReason(e.target.value)}/></label>
        {next&&<p className="page-footnote">Prochaine échéance : {new Date(next).toLocaleString('fr-FR')}</p>}
        {error&&<p className="form-error" role="alert">{error}</p>}
        <div className="form-actions"><button type="button" className="btn btn-secondary" onClick={onClose}>Fermer</button><button type="button" className="btn btn-secondary" disabled={saving||reason.trim().length<10} onClick={pause}>Suspendre</button><button className="btn btn-primary" type="submit" disabled={saving||reference.trim().length<10||reason.trim().length<10}>{saving?'En cours…':'Enregistrer'}</button></div>
      </form>}
      <div className="audit-list" aria-label="Historique des décisions">{decisions.map(d=><div key={d.id}><strong>{d.decision}</strong><small>{new Date(d.created_at).toLocaleString('fr-FR')}</small></div>)}</div>
    </section>
  </div>;
}
