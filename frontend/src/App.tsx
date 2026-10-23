import { useState } from 'react';
import type { FormEvent } from 'react';
import { api, ApiError } from './lib/api';
import type { Identity } from './lib/types';
import { Icon, Notice } from './components/ui';
import type { IconName } from './components/ui';
import { Overview, Sources, Discoveries, Threats, Watchlists, Alerts, Reports } from './pages';

type Section = 'overview'|'sources'|'discoveries'|'intelligence'|'watchlists'|'alerts'|'reports';
const navigation: {id: Section; label: string; icon: IconName; group: string}[] = [
  {id:'overview', label:'Vue générale', icon:'grid', group:'ESPACE DE TRAVAIL'},
  {id:'sources', label:'Sources Onion', icon:'layers', group:''},
  {id:'discoveries', label:'Découvertes', icon:'radar', group:''},
  {id:'intelligence', label:'Intelligence CTI', icon:'shield', group:'INVESTIGATION'},
  {id:'watchlists', label:'Watchlists', icon:'eye', group:''},
  {id:'alerts', label:'Alertes', icon:'bell', group:''},
  {id:'reports', label:'Rapports', icon:'file', group:'EXPORTS'},
];
const pageTitles: Record<Section,string> = {overview:'Vue générale',sources:'Sources Onion',discoveries:'Découvertes',intelligence:'Intelligence CTI',watchlists:'Watchlists',alerts:'Alertes',reports:'Rapports'};

function Login({onReady}: {onReady:(key:string,identity:Identity)=>void}) {
  const [key, setKey] = useState('');
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState('');
  async function connect(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setError('');
    try { const identity = await api.get<Identity>(key.trim(), '/api/v1/auth/me'); onReady(key.trim(),identity); }
    catch (err) { setError(err instanceof ApiError && err.status===401 ? 'Clé API refusée.' : err instanceof Error ? err.message : 'Connexion impossible.'); }
    finally { setBusy(false); }
  }
  return <main className="login-shell"><div className="login-glow"/><div className="login-card">
    <div className="brand brand-login"><span className="brand-mark"><Icon name="radar" size={23}/></span><span><strong>OIP<span className="accent">.</span></strong><small>ONION INTELLIGENCE PLATFORM</small></span></div>
    <div className="login-illustration"><div className="login-orbit orbit-one"/><div className="login-orbit orbit-two"/><span className="login-lock"><Icon name="lock" size={32}/></span></div>
    <p className="eyebrow">LOCAL SECURE ACCESS</p><h1>Bienvenue dans<br/><span className="accent">votre espace CTI.</span></h1>
    <p className="login-desc">Utilisez votre jeton individuel OIP. La clé historique reste disponible temporairement pendant la migration.</p>
    <form onSubmit={connect}><label htmlFor="key">CLÉ API</label><input id="key" type="password" autoComplete="off" spellCheck={false} value={key} onChange={e=>setKey(e.target.value)} placeholder="Saisir la clé API OIP" minLength={32} required/>
      {error && <p className="form-error" role="alert">{error}</p>}
      <button className="btn btn-primary login-submit" disabled={busy||key.trim().length<32}>{busy?'Vérification…':'Accéder au dashboard'}<Icon name="arrow"/></button></form>
    <p className="login-foot"><Icon name="shield" size={14}/> Clé conservée en mémoire uniquement · aucune persistance navigateur</p>
  </div><div className="login-bottom">OIP / OPERATOR CONSOLE <span>V0.9.0</span></div></main>;
}

export default function App() {
  const [token,setToken]=useState('');
  const [identity,setIdentity]=useState<Identity|null>(null);
  const [section,setSection]=useState<Section>('overview');
  const [refresh,setRefresh]=useState(0);
  const [navOpen,setNavOpen]=useState(false);
  const [notice,setNotice]=useState<{kind:'success'|'error';text:string}|null>(null);
  function navigate(next:Section) {setSection(next);setNavOpen(false);setNotice(null);}
  function notify(text:string,kind:'success'|'error'='success') {setNotice({text,kind});}
  function disconnect() {setToken('');setIdentity(null);setNotice(null);setSection('overview');}
  if (!token) return <Login onReady={(key,who)=>{setToken(key);setIdentity(who);}}/>;
  const props={token,refresh,onNotice:notify};
  return <div className="shell">
    {navOpen && <button className="nav-backdrop" aria-label="Fermer la navigation" onClick={()=>setNavOpen(false)}/>}
    <aside className={`sidebar ${navOpen?'sidebar-open':''}`}>
      <div className="brand"><span className="brand-mark"><Icon name="radar" size={24}/></span><span><strong>OIP<span className="accent">.</span></strong><small>INTELLIGENCE PLATFORM</small></span></div>
      <div className="workspace-indicator"><div className="workspace-avatar">OI</div><span><strong>Local workspace</strong><small><span className="online-dot"/> Connected</small></span><Icon name="chevron" size={14}/></div>
      <nav aria-label="Navigation principale">
        {navigation.map((item)=><div key={item.id}>{item.group && <div className="nav-group">{item.group}</div>}
          <button className={`nav-link ${section===item.id?'nav-link-active':''}`} aria-current={section===item.id?'page':undefined} onClick={()=>navigate(item.id)}><Icon name={item.icon} size={19}/><span>{item.label}</span>{section===item.id&&<i/>}</button></div>)}
      </nav>
      <div className="sidebar-bottom"><div className="secure-card"><Icon name="shield" size={22}/><strong>Périmètre contrôlé</strong><p>Accès local uniquement. Aucune exploration automatique.</p></div>
        <button className="nav-link logout-link" onClick={disconnect}><Icon name="logout"/> Déconnecter</button>
        <div className="sidebar-version">OIP CONSOLE <span>v0.9.0 / LOCAL</span></div>
      </div>
    </aside>
    <div className="main-area">
      <div className="topbar"><button className="icon-button mobile-menu" aria-label="Ouvrir le menu" onClick={()=>setNavOpen(true)}><Icon name="menu"/></button>
        <div className="breadcrumbs"><span>WORKSPACE</span><Icon name="chevron" size={14}/><strong>{pageTitles[section]}</strong></div>
        <div className="topbar-right"><span className="topbar-env"><span className="online-dot"/> ENVIRONNEMENT LOCAL · {identity?.username} ({identity?.role})</span><span className="top-divider"/><button className="icon-button refresh-button" aria-label="Actualiser les données" title="Actualiser" onClick={()=>setRefresh(n=>n+1)}><Icon name="refresh" size={18}/></button><span className="operator-avatar" title={identity?.username}>{identity?.role.slice(0,2) ?? "OP"}</span></div>
      </div>
      <div className="content" key={section}>
        {section==='overview'&&<Overview {...props} go={navigate}/>}
        {section==='sources'&&<Sources {...props}/>}
        {section==='discoveries'&&<Discoveries {...props}/>}
        {section==='intelligence'&&<Threats {...props}/>}
        {section==='watchlists'&&<Watchlists {...props}/>}
        {section==='alerts'&&<Alerts {...props}/>}
        {section==='reports'&&<Reports {...props}/>}
      </div>
      <footer className="page-footer"><span>OIP · VEILLE DOCUMENTAIRE CONTRÔLÉE</span><span>Aucune allégation n'est une preuve de compromission.</span></footer>
    </div>
    {notice&&<Notice {...notice} onClose={()=>setNotice(null)}/>}
  </div>;
}
