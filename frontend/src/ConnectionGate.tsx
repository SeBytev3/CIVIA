import { Fragment, useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { CameraSource } from '@capacitor/camera';
import { Brand } from './components/Common';
import { takeNativePhoto } from './device';
import { blobBase64, connection, randomId, setNativeProfile, type Candidate, type NativeProfile } from './nativeConnection';

const statusText = {
  starting: 'Buscando servidor CIVIA…',
  empty: 'No se encontraron servidores en esta red. La red puede restringir la comunicación entre dispositivos.',
  verifying: 'Verificando la conexión segura…',
  ready: 'Servidor CIVIA conectado.',
  unavailable: 'El servidor CIVIA no está disponible. Comprueba que el computador está encendido y en la misma red Wi-Fi.',
  identity: 'La identidad o la versión del servidor no coincide. Solicita un código nuevo al responsable de la instalación.',
};

export function ConnectionGate({ children }: { children: ReactNode }) {
  const [profile, setProfile] = useState<NativeProfile>();
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [status, setStatus] = useState<keyof typeof statusText>('starting');
  const [settings, setSettings] = useState(false);
  const [enter, setEnter] = useState(false);
  const [offlineAllowed, setOfflineAllowed] = useState(false);
  const [selected, setSelected] = useState<Candidate>();
  const [code, setCode] = useState('');
  const [url, setUrl] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const current = useRef<NativeProfile | undefined>(undefined);
  const discovered = useRef<Candidate[]>([]);
  const running = useRef(false);
  const online = useRef(false);
  const mounted = useRef(false);
  const lastAttempt = useRef(0);

  const accept = useCallback((value: NativeProfile, connect: boolean) => {
    setNativeProfile(value);
    current.current = value;
    setProfile(value);
    if (!connect) return;
    const becameOnline = !online.current;
    online.current = true;
    setStatus('ready');
    setEnter(true);
    if (becameOnline) window.dispatchEvent(new Event('civia-online'));
  }, []);

  const reconnect = useCallback(async (manualOrigin?: string) => {
    const active = current.current;
    if (!active || running.current) return;
    running.current = true;
    lastAttempt.current = Date.now();
    const origins = manualOrigin ? [manualOrigin] : [...new Set([
      active.origin,
      ...discovered.current.filter((item) => item.installationId === active.installationId).flatMap((item) => item.origins),
    ])].slice(0, 5);
    if (manualOrigin || !online.current) setStatus('verifying');
    let failure: 'identity' | 'unavailable' = 'unavailable';
    try {
      for (const origin of origins) {
        if (!mounted.current) return;
        try {
          const confirmed = await connection.reconnect({ requestId: randomId(), profileId: active.profileId, origin });
          if (mounted.current) accept(confirmed, true);
          return;
        } catch (reason) {
          if ((reason as { code?: string }).code === 'identity') failure = 'identity';
        }
      }
      if (mounted.current) {
        online.current = false;
        setStatus(failure);
      }
    } finally { running.current = false; }
  }, [accept]);

  useEffect(() => {
    let cancelled = false;
    mounted.current = true;
    const showSettings = () => { setSettings(true); setError(''); };
    const networkChanged = () => { if (current.current) void reconnect(); };
    const connectionLost = () => {
      online.current = false;
      setStatus('unavailable');
      if (Date.now() - lastAttempt.current > 3000) networkChanged();
    };
    window.addEventListener('civia-connection-settings', showSettings);
    window.addEventListener('civia-connection-lost', connectionLost);
    const listeners = [
      connection.addListener('discoveryChanged', (update) => {
        if (cancelled) return;
        const previous = JSON.stringify(discovered.current);
        discovered.current = update.candidates;
        setCandidates(update.candidates);
        if (current.current && !online.current && previous !== JSON.stringify(update.candidates)) networkChanged();
        else if (update.candidates.length && !current.current) setStatus((currentStatus) => currentStatus === 'empty' ? 'starting' : currentStatus);
        else if (update.state === 'unavailable' && !current.current) setStatus('empty');
      }),
      connection.addListener('networkChanged', networkChanged),
    ];
    void Promise.all(listeners).then(() => {
      if (!cancelled) return connection.startDiscovery();
    }).catch(() => { if (!cancelled) setStatus('empty'); });
    void connection.getTrusted().then(async (value) => {
      if (cancelled || !value.profileId || !value.installationId || !value.origin) return;
      accept(value as NativeProfile, false);
      void reconnect();
      const saved = await connection.cachedSession({ profileId: value.profileId });
      if (!cancelled && saved.json) {
        const session = JSON.parse(saved.json) as { expires_at: string };
        setOfflineAllowed(Date.parse(session.expires_at) > Date.now());
      }
    }).catch(() => {});
    const discoveryTimeout = window.setTimeout(() => {
      if (!current.current && discovered.current.length === 0) setStatus('empty');
    }, 8000);
    const retry = window.setInterval(() => { if (!online.current) networkChanged(); }, 15000);
    return () => {
      cancelled = true;
      mounted.current = false;
      window.clearTimeout(discoveryTimeout);
      window.clearInterval(retry);
      window.removeEventListener('civia-connection-settings', showSettings);
      window.removeEventListener('civia-connection-lost', connectionLost);
      for (const listener of listeners) void listener.then((handle) => handle.remove()).catch(() => {});
      void connection.stopDiscovery().catch(() => {});
    };
  }, [accept, reconnect]);

  async function scan(source: CameraSource) {
    setBusy(true);
    setError('');
    try {
      const image = await blobBase64(await takeNativePhoto(source));
      setCode((await connection.decodeQr({ requestId: randomId(), image })).code);
    } catch { setError('No se pudo leer el QR. Vuelve a escanearlo o pega el código de emparejamiento.'); }
    finally { setBusy(false); }
  }

  async function pair(value: string) {
    if (running.current) return;
    running.current = true;
    setBusy(true);
    setError('');
    setStatus('verifying');
    try {
      const entered = new URL(value.trim());
      if (selected && entered.searchParams.get('id')?.toLowerCase() !== selected.installationId) {
        setError('El código corresponde a una instalación distinta del servidor seleccionado.');
        setStatus(profile ? online.current ? 'ready' : 'unavailable' : 'starting');
        return;
      }
      const pairing = { requestId: randomId(), code: value.trim() };
      const discoveredAddress = selected?.origins[0];
      let linked: NativeProfile;
      if (discoveredAddress && discoveredAddress !== entered.searchParams.get('origin')) {
        try { linked = await connection.pair({ ...pairing, origin: discoveredAddress }); }
        catch { linked = await connection.pair({ ...pairing, requestId: randomId() }); }
      } else linked = await connection.pair(pairing);
      if (profile?.profileId !== linked.profileId) history.replaceState(null, '', '#perfil');
      setOfflineAllowed(false);
      accept(linked, true);
      setCode('');
      setSelected(undefined);
      setSettings(false);
    } catch (reason) {
      const failure = (reason as { code?: string }).code;
      setStatus(failure === 'identity' ? 'identity' : failure === 'unavailable' ? 'unavailable' : 'starting');
      if (!failure || failure === 'invalid') setError('Usa el código completo generado por la instalación de CIVIA.');
    } finally {
      setBusy(false);
      running.current = false;
    }
  }

  if (enter && !settings && profile) return <Fragment key={profile.profileId}>
    {status !== 'ready' && <aside className="surface" aria-label="Conexión con CIVIA">
      <span role="status">{status === 'verifying' ? statusText.verifying : 'Conexión interrumpida. Puedes guardar tu borrador.'}</span>
      {' '}<button type="button" className="secondary" onClick={() => setSettings(true)}>Conexión</button>
    </aside>}
    {children}
  </Fragment>;

  return <div className="citizen-shell">
    <header className="citizen-header"><Brand href="/" /></header>
    <main className="citizen-content stack">
      <section className="surface stack">
        <h1>Conectar con CIVIA</h1>
        <p role="status">{!profile && !busy && status === 'starting' && candidates.length > 0 ? 'Servidor CIVIA encontrado.' : statusText[status]}</p>
        {profile && <p>Instalación emparejada: {profile.installationId.slice(0, 8)}</p>}
        {(enter || offlineAllowed) && <button type="button" className="secondary" onClick={() => { setEnter(true); setSettings(false); }}>
          {online.current ? 'Volver a CIVIA' : 'Continuar sin conexión'}
        </button>}
        <button type="button" className="secondary" disabled={busy} onClick={async () => {
          if (running.current) return;
          setStatus('starting');
          setError('');
          await connection.stopDiscovery().catch(() => {});
          await connection.startDiscovery().catch(() => setStatus('empty'));
          if (current.current) void reconnect();
        }}>Buscar de nuevo</button>
        {candidates.length > 0 && <ul className="clean-list">
          {candidates.map((candidate) => <li key={`${candidate.name}:${candidate.installationId}:${candidate.origins.join(',')}`}>
            <button className="secondary" type="button" aria-pressed={selected === candidate} disabled={busy} onClick={() => {
              setSelected(candidate);
              setError('');
              if (candidate.installationId === profile?.installationId) void reconnect(candidate.origins[0]);
            }}>{candidate.name} · {candidate.installationId.slice(0, 8)}</button>
          </li>)}
        </ul>}
        {selected && selected.installationId !== profile?.installationId && <p>Se encontró otro servidor. Usa el código de su instalación para autorizar la conexión.</p>}
      </section>
      <section className="surface stack">
        <h2>Emparejar una instalación</h2>
        <p>Escanea el QR generado en el computador que ejecuta CIVIA o pega el código completo.</p>
        <div className="actions">
          <button type="button" className="secondary" disabled={busy} onClick={() => void scan(CameraSource.Camera)}>Escanear QR</button>
          <button type="button" className="secondary" disabled={busy} onClick={() => void scan(CameraSource.Photos)}>Abrir imagen de QR</button>
        </div>
        <form className="stack" onSubmit={(event) => { event.preventDefault(); void pair(code); }}>
          <label>Código de emparejamiento<textarea rows={3} required maxLength={1024} autoCapitalize="none" autoCorrect="off" spellCheck={false} value={code} onChange={(event) => setCode(event.target.value)} /></label>
          {error && <p role="alert">{error}</p>}
          <button type="submit" disabled={busy || status === 'verifying' || !code.trim()}>Emparejar</button>
        </form>
        {profile && <details>
          <summary>Actualizar la dirección del servidor emparejado</summary>
          <form className="stack" onSubmit={(event) => { event.preventDefault(); void reconnect(url.trim()); }}>
            <label>Dirección HTTPS<input type="url" required placeholder={profile.origin} value={url} onChange={(event) => setUrl(event.target.value)} /></label>
            <button type="submit" className="secondary" disabled={busy || status === 'verifying'}>Verificar dirección</button>
          </form>
        </details>}
      </section>
    </main>
  </div>;
}
