import { useState } from 'react';
import { createPortal } from 'react-dom';
import { api, request } from '../lib/api';
import { dataLabels } from '../lib/publicApi';
import type { PublicationPreview, PublicIncidentDraft, DataCategory } from '../lib/publicApi';
import { readableError } from '../lib/util';
import { Icon } from './ui';
import { PublicReportBody } from './PublicReportReader';

export function ReportPublication({token,reportId,onNotice}:{token:string;reportId:string;onNotice:(text:string,kind?:'success'|'error')=>void}){
 const [open,setOpen]=useState(false);const [preview,setPreview]=useState<PublicationPreview|null>(null);
 const [incident,setIncident]=useState<PublicIncidentDraft|null>(null);const [review,setReview]=useState(false);
 const [busy,setBusy]=useState(false);const [error,setError]=useState('');
 const dirty=JSON.stringify(incident)!==JSON.stringify(preview?.content.incident??null);
 function setField<K extends keyof PublicIncidentDraft>(key:K,value:PublicIncidentDraft[K]){if(incident)setIncident({...incident,[key]:value});setReview(false);}
 async function show(){setOpen(true);setPreview(null);setIncident(null);setReview(false);setError('');setBusy(true);
  try{const value=await api.get<PublicationPreview>(token,`/api/v1/reports/${reportId}/publication-preview`);setPreview(value);setIncident(value.content.incident??null);}catch(e){setError(readableError(e));}finally{setBusy(false);}}
 async function updatePreview(){if(!incident)return;setBusy(true);setError('');setReview(false);try{const value=await api.post<PublicationPreview>(token,`/api/v1/reports/${reportId}/publication-preview`,{incident});setPreview(value);setIncident(value.content.incident??null);}catch(e){setError(readableError(e));}finally{setBusy(false);}}
 function addSummary(){if(!preview)return;setIncident({title:'',company_name:'',sector:'',summary:'',data_categories:['CUSTOMER_RECORDS'],affected_records:null,detected_at:preview.content.period_end,recommendations:'',assessment:'SUSPECTED_DATA_LEAK',simulation:false});setReview(false);}
 async function publish(){if(!preview)return;setBusy(true);setError('');try{const result=await api.post<{publication_id:string}>(token,`/api/v1/reports/${reportId}/publication`,{expected_digest:preview.digest,...(preview.content.incident?{incident:preview.content.incident,review_confirmed:review}:{})});setPreview({...preview,publication_id:result.publication_id});onNotice('Rapport publié dans la vitrine.');}catch(e){setError(readableError(e));}finally{setBusy(false);}}
 async function withdraw(){if(!preview?.publication_id)return;setBusy(true);setError('');try{await request(token,`/api/v1/reports/${reportId}/publication/${preview.publication_id}`,{method:'DELETE'});setPreview({...preview,publication_id:null});setReview(false);onNotice('Rapport retiré de la vitrine.');}catch(e){setError(readableError(e));}finally{setBusy(false);}}
 return <><button className="tiny-btn" onClick={show}><Icon name="globe" size={14}/> Vitrine</button>
  {open&&createPortal(<div className="modal-shade"><section className="modal publication-editor" role="dialog" aria-modal="true" aria-label="Publication publique du rapport"><div className="modal-head"><div><p className="eyebrow">RELECTURE ET PUBLICATION</p><h2>Version publique du rapport</h2></div><button className="icon-button" disabled={busy} aria-label="Fermer" onClick={()=>setOpen(false)}><Icon name="x"/></button></div>
   <div className="publication-body"><p>Vérifiez la synthèse destinée aux visiteurs. Aucun échantillon de données, adresse de source, identifiant personnel ou note interne ne doit être publié.</p>
    {error&&<p role="alert" className="inline-error">{error}</p>}{busy&&!preview&&<p role="status">Chargement de l’aperçu…</p>}
    {preview&&<>{incident?<fieldset className="incident-editor" disabled={busy||!!preview.publication_id}><legend>Synthèse publique à vérifier</legend>
     <label>Titre public<input value={incident.title} maxLength={160} onChange={e=>setField('title',e.target.value)}/></label><label>Entreprise concernée<input value={incident.company_name} maxLength={160} onChange={e=>setField('company_name',e.target.value)}/></label><label>Secteur<input value={incident.sector} maxLength={80} onChange={e=>setField('sector',e.target.value)}/></label>
     <label>Synthèse publique<textarea value={incident.summary} maxLength={1500} rows={5} onChange={e=>setField('summary',e.target.value)}/></label>
     <label>Volume estimé d’enregistrements<input type="number" min={1} max={1000000000} value={incident.affected_records??''} onChange={e=>setField('affected_records',e.target.value?Number(e.target.value):null)}/></label>
     <div className="incident-category-options">{Object.entries(dataLabels).map(([key,label])=><label key={key}><input type="checkbox" checked={incident.data_categories.includes(key as DataCategory)} onChange={e=>setField('data_categories',e.target.checked?[...incident.data_categories,key as DataCategory]:incident.data_categories.filter(c=>c!==key))}/>{label}</label>)}</div>
     <label>Recommandations<textarea value={incident.recommendations} maxLength={800} rows={3} onChange={e=>setField('recommendations',e.target.value)}/></label>
     <label><input type="checkbox" checked={incident.simulation} onChange={e=>setField('simulation',e.target.checked)}/>Rapport de simulation : entreprise et données fictives</label>
     {dirty&&<button className="btn btn-secondary" disabled={busy} onClick={updatePreview}>Mettre à jour l’aperçu</button>}
    </fieldset>:!preview.publication_id&&<button className="btn btn-secondary" onClick={addSummary}>Ajouter une synthèse publique</button>}
    <h3>Aperçu exact de la version publique</h3>{dirty&&<p role="status">Les modifications doivent être validées dans l’aperçu avant publication.</p>}<PublicReportBody content={preview.content}/>
    <p role="status">{preview.publication_id?'Ce rapport possède une version publique.':'Ce rapport n’est pas publié.'}</p>
    {preview.content.incident&&!preview.publication_id&&<label className="publication-review"><input type="checkbox" checked={review} disabled={dirty||busy} onChange={e=>setReview(e.target.checked)}/>J’ai vérifié ces informations et j’autorise leur publication publique.</label>}
    <div className="form-actions">{preview.publication_id?<button className="btn btn-secondary" disabled={busy} onClick={withdraw}>Retirer de la vitrine</button>:<button className="btn btn-primary" disabled={busy||dirty||!!preview.content.incident&&!review} onClick={publish}>{preview.content.incident?'Publier le rapport relu':'Publier ces compteurs'}</button>}</div></>}
   </div></section></div>,document.body)}
 </>;
}
