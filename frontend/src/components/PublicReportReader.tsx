import { useEffect, useRef } from 'react';
import type { PublishedReport, PublicReportContent } from '../lib/publicApi';
import { totalLabels } from '../lib/publicApi';
import { usePublicResource } from '../lib/usePublicResource';
import { DateCell, Icon } from './ui';

export function PublicReportBody({content}:{content:PublicReportContent}){
  return <><p className="public-report-period">Période : du <DateCell value={content.period_start}/> au <DateCell value={content.period_end}/></p>
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
