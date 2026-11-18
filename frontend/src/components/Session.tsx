import { useEffect, useState } from 'react';
import { authenticate, logout, readSession } from '../api';
import type { Role, User } from '../types';

export const roleLabels: Record<Role, string> = {
  CITIZEN: 'Ciudadano',
  CASE_ADMIN: 'Administrador de casos',
  WEB_ADMIN: 'Administrador web',
};

export function useSession() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let cancelled = false;
    readSession().then((value) => {
      if (!cancelled) setUser(value);
    }).catch((reason: Error) => {
      if (!cancelled) setError(reason.message);
    }).finally(() => {
      if (!cancelled) setLoading(false);
    });
    return () => { cancelled = true; };
  }, [version]);

  async function signOut() {
    await logout();
    setUser(null);
  }

  function refresh() {
    setError('');
    setLoading(true);
    setVersion((value) => value + 1);
  }

  useEffect(() => {
    const revoke = () => {
      setUser(null);
      refresh();
    };
    window.addEventListener('civia-session-expired', revoke);
    return () => window.removeEventListener('civia-session-expired', revoke);
  }, []);

  return { user, setUser, loading, error, refresh, signOut };
}

export function Login({ allowRegister, onSession, onBack }: {
  allowRegister?: boolean;
  onSession: (user: User) => void;
  onBack?: () => void;
}) {
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  return (
    <section className="surface login-panel">
      <h1>{mode === 'register' ? 'Crear cuenta ciudadana' : 'Iniciar sesión'}</h1>
      <form className="stack" onSubmit={async (event) => {
        event.preventDefault();
        setBusy(true);
        setError('');
        const data = new FormData(event.currentTarget);
        const values = { email: String(data.get('email')), password: String(data.get('password')) };
        try {
          onSession(await authenticate(mode, mode === 'register' ? { ...values, name: String(data.get('name')) } : values));
        } catch (reason) {
          setError((reason as Error).message);
        } finally {
          setBusy(false);
        }
      }}>
        {mode === 'register' && <label>Nombre<input name="name" autoComplete="name" required minLength={2} maxLength={120} /></label>}
        <label>Correo electrónico<input name="email" type="email" inputMode="email" autoComplete="username" required /></label>
        <label>Contraseña<input name="password" type="password" autoComplete={mode === 'register' ? 'new-password' : 'current-password'} required minLength={mode === 'register' ? 15 : undefined} maxLength={128} /></label>
        {error && <p role="alert">{error}</p>}
        <button type="submit" disabled={busy}>{busy ? 'Conectando…' : mode === 'register' ? 'Registrarme' : 'Entrar'}</button>
        {allowRegister && <button className="secondary" type="button" onClick={() => {
          setMode(mode === 'login' ? 'register' : 'login');
          setError('');
        }}>{mode === 'login' ? 'Crear cuenta ciudadana' : 'Ya tengo cuenta'}</button>}
        {onBack && <button className="secondary" type="button" onClick={onBack}>Volver</button>}
      </form>
    </section>
  );
}

export function Profile({ user, signOut }: { user: User; signOut: () => Promise<void> }) {
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  return (
    <section className="surface">
      <h1>Perfil</h1>
      <dl><dt>Nombre</dt><dd>{user.name}</dd><dt>Correo</dt><dd>{user.email}</dd><dt>Perfil</dt><dd>{roleLabels[user.role]}</dd></dl>
      {error && <p role="alert">{error}</p>}
      <button disabled={busy} onClick={async () => {
        setBusy(true);
        setError('');
        try { await signOut(); }
        catch (reason) { setError((reason as Error).message); }
        finally { setBusy(false); }
      }}>Cerrar sesión</button>
    </section>
  );
}
