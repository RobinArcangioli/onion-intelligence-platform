import { useEffect, useRef } from 'react';
import type { PublishedReport, PublicReportContent } from '../lib/publicApi';
import { totalLabels, dataLabels } from '../lib/publicApi';
import { usePublicResource } from '../lib/usePublicResource';
import { DateCell, Icon } from './ui';

export function PublicReportBody({content}:{content:PublicReportContent}){
  return <>{content.incident&&<section className="incident-summary" aria-label="Synthèse publique de la fuite">
      {content.incident.simulation&&<p className="simulation-label">SIMULATION — entreprise et données entièrement fictives</p>}
      <h3>{content.incident.title}</h3><dl className="incident-facts"><div><dt>Entreprise concernée</dt><dd>{content.incident.company_name}</dd></div><div><dt>Secteur</dt><dd>{content.incident.sector}</dd></div><div><dt>Signal</dt><dd>Fuite de données suspectée</dd></div><div><dt>Détection</dt><dd><DateCell value={content.incident.detected_at}/></dd></div><div><dt>Volume annoncé</dt><dd>{content.incident.affected_records?.toLocaleString('fr-FR')??'Non précisé'} enregistrements</dd></div></dl>
      <h4>Synthèse relue par l’administrateur</h4><p className="incident-text">{content.incident.summary}</p><h4>Catégories de données mentionnées</h4><ul>{content.incident.data_categories.map(category=><li key={category}>{dataLabels[category]}</li>)}</ul>
      <h4>Recommandations</h4><p className="incident-text">{content.incident.recommendations}</p><p className="muted small">La validation autorise la publication de cette synthèse ; elle ne confirme pas à elle seule la véracité d’une revendication.</p>
    </section>}<p className="public-report-period">Période : du <DateCell value={content.period_start}/> au <DateCell value={content.period_end}/></p>
    <dl className="public-totals">{Object.entries(totalLabels).map(([key,label])=><div key={key}><dt>{label}</dt><dd>{content.totals[key as keyof typeof totalLabels].toLocaleString('fr-FR')}</dd></div>)}</dl>
    <p className="muted small public-disclaimer">{content.disclaimer}</p></>;
}

export function PublicReportReader({id,onClose}:{id:string;onClose:()=>void}){
  const report=usePublicResource<PublishedReport>(`/api/public/v1/reports/${id}`,0);
  const close=useRef<HTMLButtonElement>(null);
  useEffect(()=>{close.current?.focus();},[]);
  return <div className="modal-shade" onMouseDown={e=>{if(e.target===e.currentTarget)onClose();}}>
    <section className="modal public-report-reader" role="dialog" aria-modal="true" aria-label="Consulter le rapport public" onKeyDown={e=>{if(e.key==='Escape')onClose();}}>
      <div className="modal-head"><div><p className="eyebrow">RAPPORT PUBLIC</p><h2>Rapport de veille publié</h2></div><button ref={close} className="icon-button" aria-label="Fermer le rapport" onClick={onClose}><Icon name="x"/></button></div>
      {report.loading?<p role="status" className="visitor-loading">Ouverture du rapport…</p>:report.error?<div className="publication-body"><p role="alert" className="inline-error">{report.error}</p></div>:report.data&&<div className="publication-body"><p>Publié le <DateCell value={report.data.published_at}/></p><PublicReportBody content={report.data.content}/></div>}
    </section>
  </div>;
}
