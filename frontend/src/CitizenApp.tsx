import { useEffect, useState } from 'react';
import { App as NativeApp } from '@capacitor/app';
import type { PluginListenerHandle } from '@capacitor/core';
import { getPublicMap, getReportByCode, getReports, getPublicStats, getStats, queryAgent } from './api';
import { CaliMap } from './components/CaliMap';
import { AnalysisState, ReportDetail, statuses } from './components/ReportDetail';
import { ReportForm } from './components/ReportForm';
import { Login, Profile, useSession } from './components/Session';
import { SafeMarkdown } from './components/SafeMarkdown';
import { isNative } from './device';
import type { AgentQueryResponse, Page, PublicMapItem, ReportItem, PublicStats, ReportStats, User } from './types';
import { Brand, useLoad, PageControls } from './components/Common';

type Tab = 'inicio' | 'reportar' | 'reportes' | 'asistente' | 'perfil';
const tabs: Record<Tab, string> = { inicio: 'Inicio', reportar: 'Reportar', reportes: 'Mis reportes', asistente: 'Asistente', perfil: 'Perfil' };
const tabIcons: Record<Tab, string> = { inicio: '⌂', reportar: '+', reportes: '☰', asistente: '✦', perfil: '○' };
const mobileViewport = '(max-width: 767px) and (pointer: coarse)';

function selectedTab(): Tab {
  const hash = location.hash.slice(1);
  return Object.hasOwn(tabs, hash) ? hash as Tab : 'inicio';
}

function Home({ user, onReport, onReports }: { user: User | null; onReport: () => void; onReports: () => void }) {
  const data = useLoad(() => Promise.all([getPublicStats(), getPublicMap(), user ? getStats() : Promise.resolve(null)]), [user]);
  const stats: PublicStats | undefined = data.value?.[0];
  const map: Page<PublicMapItem> | undefined = data.value?.[1];
  const own: ReportStats | null | undefined = data.value?.[2];
  return <div className="stack">
    <section className="citizen-hero">
      <p className="eyebrow">Cali y Valle del Cauca</p>
      <h1>Reportes ciudadanos</h1>
      <p>Registra incidentes viales y ambientales y consulta su avance.</p>
      <button className="hero-button" onClick={onReport}>Reportar</button>
    </section>
    {data.error && <p role="alert">{data.error}</p>}
    {data.loading && <p role="status">Cargando actividad ciudadana…</p>}
    {own && <section className="surface section-heading"><div><h2>Mis reportes</h2><p>{own.total_reports} registrados · {own.by_status.PENDING_ANALYSIS ?? 0} recibidos</p></div><button className="secondary" onClick={onReports}>Consultar</button></section>}
    <section className="surface stack">
      <div className="section-heading"><h2>Mapa ciudadano</h2>{stats && <span>{stats.total} reportes públicos</span>}</div>
      <CaliMap reports={[]} publicPoints={map?.items} height="340px" />
    </section>
  </div>;
}

function MyReports() {
  const [selected, setSelected] = useState<ReportItem | null>(null);
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState('');
  const [searching, setSearching] = useState(false);
  const data = useLoad(() => getReports({ limit: 10, offset }), [offset]);
  if (selected) return <ReportDetail report={selected} editable onUpdate={setSelected} onClose={() => { setSelected(null); data.reload(); }} />;
  return <section className="surface stack">
    <div className="section-heading"><h1>Mis reportes</h1><button className="secondary" onClick={data.reload}>Actualizar</button></div>
    <form className="actions" onSubmit={async (event) => {
      event.preventDefault();
      setSearching(true);
      setError('');
      const code = String(new FormData(event.currentTarget).get('code'));
      try { setSelected(await getReportByCode(code)); }
      catch (reason) { setError((reason as Error).message); }
      finally { setSearching(false); }
    }}>
      <label>Radicado<input name="code" autoComplete="off" required maxLength={60} /></label>
      <button disabled={searching}>Consultar por radicado</button>
    </form>
    {(error || data.error) && <p role="alert">{error || data.error}</p>}
    {data.loading ? <p role="status">Cargando reportes…</p> : data.value?.items.length === 0 && <p>Aún no tienes reportes.</p>}
    <ul className="clean-list">
      {data.value?.items.map((item) => <li key={item.id}>
        <button type="button" className="report-card" onClick={() => setSelected(item)}>
          <span><strong>{item.title}</strong><small>{item.tracking_code} · {statuses[item.status]}</small></span><AnalysisState report={item} />
        </button>
      </li>)}
    </ul>
    <PageControls page={data.value} onOffset={setOffset} />
  </section>;
}

function Assistant() {
  const [result, setResult] = useState<AgentQueryResponse | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  return <section className="surface stack">
    <h1>Asistente ciudadano</h1>
    <form className="stack" onSubmit={async (event) => {
      event.preventDefault();
      setBusy(true);
      setError('');
      setResult(null);
      try { setResult(await queryAgent(String(new FormData(event.currentTarget).get('query')))); }
      catch { setError('El asistente no está disponible temporalmente. Puedes consultar tus reportes y realizar otras gestiones mientras se restablece el servicio.'); }
      finally { setBusy(false); }
    }}>
      <label>Pregunta<textarea name="query" required minLength={3} maxLength={1000} placeholder="¿En qué estado está mi reporte?" rows={4} /></label>
      <button disabled={busy}>{busy ? 'Consultando…' : 'Consultar al asistente'}</button>
    </form>
    {error && <p role="alert">{error}</p>}
    {result && <div aria-live="polite">
      <SafeMarkdown content={result.answer} />
      {result.requires_human_approval && <p role="status">Solicitud registrada. El equipo de casos debe revisarla antes de aplicar el cambio.</p>}
    </div>}
  </section>;
}

export function CitizenApp() {
  const session = useSession();
  const [tab, setTab] = useState(selectedTab);
  const [mobile, setMobile] = useState(() => isNative || matchMedia(mobileViewport).matches);
  const [sessionError, setSessionError] = useState('');
  const user = session.user?.role === 'CITIZEN' ? session.user : null;

  function navigate(next: Tab) {
    if (next !== selectedTab()) history.pushState(null, '', next === 'inicio' ? location.pathname : `#${next}`);
    setTab(next);
    scrollTo(0, 0);
  }

  useEffect(() => {
    const viewport = matchMedia(mobileViewport);
    const update = () => setMobile(isNative || viewport.matches);
    const readTab = () => { setTab(selectedTab()); window.scrollTo(0, 0); };
    viewport.addEventListener('change', update);
    window.addEventListener('popstate', readTab);
    window.addEventListener('hashchange', readTab);
    let handle: PluginListenerHandle | undefined;
    let cancelled = false;
    if (isNative) void NativeApp.addListener('backButton', ({ canGoBack }) => {
      if (canGoBack) history.back();
      else if (selectedTab() !== 'inicio') navigate('inicio');
      else void NativeApp.minimizeApp();
    }).then((listener) => {
      if (cancelled) void listener.remove();
      else handle = listener;
    });
    return () => {
      cancelled = true;
      void handle?.remove();
      viewport.removeEventListener('change', update);
      window.removeEventListener('popstate', readTab);
      window.removeEventListener('hashchange', readTab);
    };
  }, []);

  let content;
  if (tab === 'inicio') content = <Home user={user} onReport={() => navigate('reportar')} onReports={() => navigate('reportes')} />;
  else if (tab === 'reportar' && !mobile) content = <section className="surface stack"><h1>Nuevo reporte</h1><p>Para registrar un reporte, utiliza CIVIA desde tu dispositivo móvil.</p></section>;
  else if (session.loading) content = <p role="status">Comprobando sesión…</p>;
  else if (session.error) content = <section className="surface stack"><p role="alert">{session.error}</p><button onClick={session.refresh}>Reintentar conexión</button></section>;
  else if (session.user && !user) content = <section className="surface stack">
    <h1>Cuenta ciudadana requerida</h1>
    {!isNative && <a href="/admin/">Ir al portal administrativo</a>}
    {sessionError && <p role="alert">{sessionError}</p>}
    <button onClick={() => void session.signOut().catch((reason: Error) => setSessionError(reason.message))}>Cerrar sesión para cambiar de cuenta</button>
  </section>;
  else if (!user) content = <Login allowRegister onSession={session.setUser} onBack={() => navigate('inicio')} />;
  else if (tab === 'reportar') content = <ReportForm key={user.id} ownerId={user.id} onNavigate={() => navigate('reportes')} />;
  else if (tab === 'reportes') content = <MyReports key={user.id} />;
  else if (tab === 'asistente') content = <Assistant key={user.id} />;
  else content = <Profile user={user} signOut={session.signOut} />;

  return <div className="citizen-shell">
    <header className="citizen-header"><Brand href="/" /><div className="actions">
      {!isNative && <a className="desktop-admin-link" href="/admin/">Portal administrativo</a>}
      {user ? <button className="quiet" onClick={() => navigate('perfil')}>{user.name}</button> : <button className="quiet" onClick={() => navigate('perfil')}>Entrar</button>}
    </div></header>
    <main className="citizen-content">{content}</main>
    <nav className="citizen-nav" aria-label="Navegación ciudadana">
      {(Object.keys(tabs) as Tab[]).map((key) => <button key={key} className={key === tab ? 'selected' : ''} aria-current={key === tab ? 'page' : undefined} onClick={() => navigate(key)}>
        <span aria-hidden="true">{tabIcons[key]}</span>{tabs[key]}
      </button>)}
    </nav>
  </div>;
}
