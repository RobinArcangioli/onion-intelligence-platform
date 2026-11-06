import { useEffect, useState } from 'react';
import { api, ApiError } from '../lib/api';
import { Icon, Panel } from './ui';

type Result={code:string;company_name:string;status:string;report_id:string};
type Demo={mode:'SYNTHETIC_ONLY';completed:boolean;scenarios:{code:string;company_name:string}[];results:Result[]};
export function SimulationControls({token,onCompleted}:{token:string;onCompleted:()=>void}){
 const [demo,setDemo]=useState<Demo|null>(null);const [busy,setBusy]=useState(false);const [error,setError]=useState('');
 useEffect(()=>{let alive=true;api.get<Demo>(token,'/api/v1/demo/simulations').then(d=>{if(alive&&d.mode==='SYNTHETIC_ONLY')setDemo(d);}).catch(e=>{if(alive&&!(e instanceof ApiError&&e.status===404))setError('Simulation indisponible.');});return()=>{alive=false;};},[token]);
 async function run(){if(!demo)return;setBusy(true);setError('');try{const result=await api.post<{results:Result[]}>(token,'/api/v1/demo/simulations/run',{});setDemo({...demo,completed:true,results:result.results});onCompleted();}catch{setError('La simulation n’a pas abouti. Aucun service externe n’a été contacté.');}finally{setBusy(false);}}
 if(!demo)return null;
 return <Panel title="Simulation complète de deux fuites fictives" kicker="EXERCICE LOCAL — AUCUN ACCÈS AU DARK WEB" action={<button className="btn btn-primary" disabled={busy||demo.completed} onClick={run}><Icon name="activity"/>{busy?'Simulation en cours…':demo.completed?'Deux veilles simulées terminées':'Lancer les deux veilles simulées'}</button>}>
  <div className="publication-body"><p>Déclenchez deux demandes de veille. Le worker traite des pages fictives, les observations déclenchent les alertes, puis deux rapports privés sont générés pour relecture.</p><ul>{demo.scenarios.map(s=><li key={s.code}>{s.company_name}</li>)}</ul>
   {error&&<p role="alert" className="inline-error">{error}</p>}{demo.completed&&<div role="status"><strong>2 observations · 2 alertes de fuite · 2 rapports privés prêts.</strong><p>Consultez les alertes, puis ouvrez « Vitrine » sur chaque rapport pour relire la synthèse, confirmer sa publication et la vérifier côté visiteur.</p></div>}
  </div></Panel>;
}
