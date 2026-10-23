import type { ReactNode } from 'react';
import { compactId, dateTime, pct } from '../lib/util';

export type IconName = 'grid'|'layers'|'radar'|'shield'|'eye'|'bell'|'file'|'refresh'|'logout'|'plus'|'search'|'arrow'|'check'|'x'|'database'|'activity'|'download'|'menu'|'lock'|'chevron'|'pulse'|'globe'|'filter';
const strokes: Record<IconName, ReactNode> = {
  grid: <><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></>,
  layers: <><path d="m12 3 9 5-9 5-9-5z"/><path d="m3 12 9 5 9-5M3 16l9 5 9-5"/></>,
  radar: <><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="2"/><path d="m12 12 6-6M12 3v2M3 12h2"/></>,
  shield: <><path d="m12 2 8 4v6c0 5-3 8-8 10-5-2-8-5-8-10V6z"/><path d="m9 12 2 2 4-4"/></>,
  eye: <><path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7-10-7-10-7"/><circle cx="12" cy="12" r="3"/></>,
  bell: <><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/></>,
  file: <><path d="M5 2h9l5 5v15H5z"/><path d="M14 2v6h5M8 12h8M8 16h8"/></>,
  refresh: <><path d="M20 7v5h-5M4 17v-5h5"/><path d="M6 9a7 7 0 0 1 12-2l2 5M4 12l2 5a7 7 0 0 0 12-2"/></>,
  logout: <><path d="M10 4H4v16h6M14 7l5 5-5 5M19 12H9"/></>,
  plus: <path d="M12 5v14M5 12h14"/>,
  search: <><circle cx="11" cy="11" r="7"/><path d="m16 16 5 5"/></>,
  arrow: <><path d="M4 12h16m-6-6 6 6-6 6"/></>,
  check: <path d="m4 12 5 5 11-11"/>,
  x: <path d="M5 5 19 19M19 5 5 19"/>,
  database: <><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14c0 2 18 2 18 0V5M3 12c0 4 18 4 18 0"/></>,
  activity: <path d="M2 12h5l3-7 4 14 3-7h5"/>,
  download: <><path d="M12 3v12m-5-5 5 5 5-5M4 17v4h16v-4"/></>,
  menu: <path d="M4 6h16M4 12h16M4 18h16"/>,
  lock: <><rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/></>,
  chevron: <path d="m9 5 7 7-7 7"/>,
  pulse: <><circle cx="12" cy="12" r="9"/><path d="M6 12h3l2-4 3 8 2-4h2"/></>,
  globe: <><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c5 5 5 13 0 18-5-5-5-13 0-18"/></>,
  filter: <><path d="M3 5h18l-7 8v5l-4 2v-7z"/></>,
};
export function Icon({ name, size = 19 }: { name: IconName; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{strokes[name]}</svg>;
}
export function Status({value}: {value: string | boolean | null | undefined}) {
  const text = typeof value === 'boolean' ? (value ? 'ACTIVE' : 'INACTIVE') : value || 'UNKNOWN';
  const good = /^(ACTIVE|APPROVED|COMPLETED|ACCEPTED|RESOLVED|UNCHANGED|200)$/.test(text);
  const warn = /^(PENDING|OPEN|HIGH|REVIEW_REQUIRED|MODIFIED|AUTO_SUGGESTED|ACKNOWLEDGED)$/.test(text);
  const bad = /^(FAILED|REJECTED|REVOKED|DISABLED|CANCELLED)$/.test(text);
  return <span className={`status ${good?'status-good':warn?'status-warn':bad?'status-bad':'status-neutral'}`}><span className="status-dot"/>{text.replaceAll('_',' ')}</span>;
}
export function Mono({value, title}: {value?: string|null; title?: string}) { return <span className="mono trunc" title={title || value || ''}>{compactId(value)}</span>; }
export function DateCell({value}: {value?: string|null}) { return <span className="muted small" title={value || ''}>{dateTime(value)}</span>; }
export function Score({value}: {value:number}) {return <span className="score"><span className="score-track"><span style={{width:`${pct(value)}%`}}/></span><b>{value}</b></span>}
export function Empty({title='Aucune donnée disponible', text='Les résultats apparaîtront ici après les premières opérations.'}: {title?:string; text?:string}) {return <div className="empty"><div className="empty-icon"><Icon name="database" size={25}/></div><h3>{title}</h3><p>{text}</p></div>}
export function PageHead({eyebrow,title,description,actions}: {eyebrow:string;title:string;description:string;actions?:ReactNode}) {return <header className="page-head"><div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p className="page-subtitle">{description}</p></div><div className="head-actions">{actions}</div></header>}
export function Panel({title,kicker,action,children, className=''}: {title:string;kicker?:string;action?:ReactNode;children:ReactNode;className?:string}) {return <section className={`panel ${className}`}><div className="panel-head"><div>{kicker && <p className="panel-kicker">{kicker}</p>}<h2>{title}</h2></div>{action}</div>{children}</section>}
export function Pager({total, offset, pageSize, onChange}: {total:number; offset:number; pageSize:number; onChange:(n:number)=>void}) {return <div className="pager"><span>{total === 0 ? '0 résultat' : `${offset+1}–${Math.min(offset+pageSize,total)} sur ${total}`}</span><div><button className="btn btn-ghost" disabled={offset===0} onClick={()=>onChange(Math.max(0,offset-pageSize))}>Précédent</button><button className="btn btn-ghost" disabled={offset+pageSize>=total} onClick={()=>onChange(offset+pageSize)}>Suivant</button></div></div>}
export function Notice({kind,text,onClose}: {kind:'success'|'error';text:string;onClose:()=>void}) {return <div className={`toast toast-${kind}`} role="status"><Icon name={kind==='error'?'x':'check'}/><span>{text}</span><button className="icon-button" aria-label="Fermer" onClick={onClose}><Icon name="x" size={15}/></button></div>}
