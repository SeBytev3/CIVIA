import { useState } from 'react';
import { Brand } from './components/Common';
import { ReportForm } from './components/ReportForm';
import { Login, useSession } from './components/Session';
import { experience } from './experience';

export function PublicReport() {
  const session = useSession();
  const [signOutError, setSignOutError] = useState('');
  const citizen = session.user?.role === 'CITIZEN' ? session.user : null;

  async function changeAccount() {
    try {
      setSignOutError('');
      await session.signOut();
    } catch {
      setSignOutError('No se pudo cerrar la sesión. Intenta nuevamente.');
    }
  }

  let content;
  if (session.loading) content = <p role="status">Comprobando sesión…</p>;
  else if (session.error && !citizen) content = <section className="surface stack">
    <p role="alert">{session.error}</p>
    <button onClick={session.refresh}>Reintentar conexión</button>
  </section>;
  else if (citizen) content = <ReportForm key={citizen.id} ownerId={citizen.id} />;
  else if (session.user) content = <section className="surface stack">
    <h2>Inicia sesión con una cuenta ciudadana</h2>
    <button onClick={() => void changeAccount()}>Cambiar de cuenta</button>
    {signOutError && <p role="alert">{signOutError}</p>}
  </section>;
  else content = <Login allowRegister heading="h2" onSession={session.setUser} />;

  return <div className="public-shell">
    <header className="public-header">
      <div className="public-wrap section-heading">
        <Brand href="/" />
        {citizen && <button className="quiet" onClick={() => void changeAccount()}>Cerrar sesión</button>}
      </div>
    </header>
    <main className="public-wrap public-content">
      <div className="public-intro stack">
        <p className="eyebrow">Cali y Valle del Cauca</p>
        <h1>Reporta un incidente en tu comunidad</h1>
        <p>Registra un problema vial o ambiental con una foto y su ubicación. Recibirás un radicado para identificar el reporte.</p>
        {signOutError && citizen && <p role="alert">{signOutError}</p>}
      </div>
      <div className="public-report">{content}</div>
    </main>
    <footer className="public-footer">
      <div className="public-wrap section-heading">
        <p>CIVIA · Iniciativa académica de la Universidad Cooperativa de Colombia</p>
        {experience() === 'browser' && <a href="/app/#instalar">Instalar CIVIA</a>}
      </div>
    </footer>
  </div>;
}
