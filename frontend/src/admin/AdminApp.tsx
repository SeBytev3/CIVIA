import { useState } from 'react';
import { Brand } from '../components/Common';
import { Login, Profile, roleLabels, useSession } from '../components/Session';
import { Approvals, Cases, Dashboard, History, Notifications } from './Cases';
import { Audit, DeadLetters, Observability, Queue, Settings, System, Users } from './System';

const caseSections = {
  dashboard: 'Dashboard', cases: 'Bandeja de casos', map: 'Mapa', notifications: 'Notificaciones',
  approvals: 'Aprobaciones', history: 'Historial',
};
const webSections = {
  users: 'Usuarios y roles', audit: 'Auditoría', system: 'Estado del sistema', observability: 'Observabilidad',
  queue: 'Cola de procesamiento', dead: 'Trabajos fallidos', settings: 'Configuración',
};
type Section = keyof typeof caseSections | keyof typeof webSections | 'profile';

export function AdminApp() {
  const session = useSession();
  const [section, setSection] = useState<Section>('dashboard');
  const [error, setError] = useState('');
  const user = session.user;

  if (session.loading || session.error || !user || user.role === 'CITIZEN') {
    return <main className="admin-login">
      <Brand href="/admin/" subtitle="Portal administrativo" />
      {session.loading ? <p role="status">Comprobando sesión…</p> :
        session.error ? <section className="surface stack"><p role="alert">{session.error}</p><button onClick={session.refresh}>Reintentar conexión</button></section> :
        user?.role === 'CITIZEN' ? <section className="surface stack">
          <h1>Acceso administrativo</h1>
          <p role="alert">Este portal requiere una cuenta administrativa.</p>
          {error && <p role="alert">{error}</p>}
          <button onClick={() => void session.signOut().catch((reason: Error) => setError(reason.message))}>Cerrar sesión para cambiar de cuenta</button>
          <a href="/">Ir al espacio ciudadano</a>
        </section> : <Login onSession={(account) => { setSection('dashboard'); session.setUser(account); }} />}
    </main>;
  }

  const isWebAdmin = user.role === 'WEB_ADMIN';
  const sections = { ...caseSections, ...(isWebAdmin ? webSections : {}), profile: 'Perfil' };
  const content = {
    dashboard: <Dashboard />, cases: <Cases key="list" />, map: <Cases key="map" map />, notifications: <Notifications />,
    approvals: <Approvals />, history: <History />, users: <Users />, audit: <Audit />, system: <System />,
    observability: <Observability />, queue: <Queue />, dead: <DeadLetters />, settings: <Settings />,
    profile: <Profile user={user} signOut={session.signOut} />,
  };
  return <div className="admin-shell">
    <aside className="admin-sidebar">
      <Brand href="/admin/" subtitle="Portal administrativo" />
      <nav aria-label="Secciones administrativas">{Object.entries(sections).map(([key, label]) => <button key={key} className={section === key ? 'selected' : ''} aria-current={section === key ? 'page' : undefined} onClick={() => setSection(key as Section)}>{label}</button>)}</nav>
    </aside>
    <div className="admin-workspace">
      <header className="admin-topbar"><span>{roleLabels[user.role]}</span><button className="quiet" onClick={() => setSection('profile')}>{user.name}</button></header>
      <main className="admin-content" key={user.id}>{content[Object.hasOwn(sections, section) ? section : 'dashboard']}</main>
    </div>
  </div>;
}
