import { useRef, useState } from 'react';
import { createUser, getAudit, getDeadLetters, getObservability, getQueue, getSystem, getUsers, requeue, resetPassword, setFault, updateUser } from '../api';
import { LoadNotice, PageControls, useLoad } from '../components/Common';
import { roleLabels } from '../components/Session';
import { formattedDate } from '../components/ReportDetail';
import type { Role, User } from '../types';

const roles = Object.entries(roleLabels);
function RoleOptions() {
  return <>{roles.map(([role, label]) => <option key={role} value={role}>{label}</option>)}</>;
}

export function Users() {
  const [offset, setOffset] = useState(0);
  const [passwordFor, setPasswordFor] = useState<User | null>(null);
  const data = useLoad(() => getUsers(offset, 20), [offset]);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [busy, setBusy] = useState(false);

  async function perform(action: () => Promise<unknown>, message: string, onSuccess?: () => void) {
    setError('');
    setSuccess('');
    setBusy(true);
    try { await action(); setSuccess(message); onSuccess?.(); data.reload(); }
    catch (reason) { setError((reason as Error).message); }
    finally { setBusy(false); }
  }

  return <section className="surface stack">
    <h1>Usuarios y roles</h1>
    <details><summary>Crear usuario</summary><form className="stack" onSubmit={(event) => {
      event.preventDefault();
      const form = event.currentTarget;
      const fields = new FormData(form);
      void perform(() => createUser({
        name: String(fields.get('name')), email: String(fields.get('email')),
        password: String(fields.get('password')), role: fields.get('role') as Role,
      }), 'Cuenta creada.', () => form.reset());
    }}>
      <label>Nombre<input name="name" required minLength={2} maxLength={120} autoComplete="name" /></label>
      <label>Correo<input name="email" required type="email" autoComplete="off" /></label>
      <label>Contraseña inicial<input name="password" type="password" required minLength={15} maxLength={128} autoComplete="new-password" /></label>
      <label>Perfil<select name="role"><RoleOptions /></select></label>
      <button disabled={busy}>Crear cuenta</button>
    </form></details>
    {error && <p role="alert">{error}</p>}{success && <p role="status">{success}</p>}
    <LoadNotice {...data} />
    {passwordFor && <form className="stack" key={passwordFor.id} onSubmit={(event) => {
      event.preventDefault();
      const fields = new FormData(event.currentTarget);
      if (!window.confirm('¿Restablecer la contraseña y revocar las sesiones de esta cuenta?')) return;
      void perform(() => resetPassword(passwordFor.id, String(fields.get('password'))), 'Contraseña restablecida.', () => setPasswordFor(null));
    }}><h2>Restablecer contraseña de {passwordFor.name}</h2>
      <label>Nueva contraseña<input name="password" type="password" required minLength={15} maxLength={128} autoComplete="new-password" /></label>
      <div className="actions"><button disabled={busy}>Restablecer</button><button className="secondary" type="button" onClick={() => setPasswordFor(null)}>Cancelar</button></div>
    </form>}
    <div className="table-scroll"><table><thead><tr><th>Usuario</th><th>Perfil</th><th>Estado</th><th>Acciones</th></tr></thead>
      <tbody>{data.value?.items.map((user) => <tr key={user.id}>
        <td><strong>{user.name}</strong><br />{user.email}</td>
        <td><form className="actions" onSubmit={(event) => {
          event.preventDefault();
          const role = new FormData(event.currentTarget).get('role') as Role;
          if (role !== user.role && window.confirm(`¿Asignar el perfil ${roleLabels[role]} a ${user.name}?`)) {
            void perform(() => updateUser(user.id, { role }), 'Perfil actualizado.');
          }
        }}><select name="role" aria-label={`Perfil de ${user.name}`} defaultValue={user.role}><RoleOptions /></select>
          <button className="secondary" disabled={busy}>Guardar</button></form></td>
        <td>{user.active ? 'Activa' : 'Inactiva'}</td>
        <td><div className="actions"><button className="secondary" disabled={busy} onClick={() => {
          if (window.confirm(user.active ? '¿Desactivar la cuenta y revocar sus sesiones?' : '¿Activar esta cuenta?')) {
            void perform(() => updateUser(user.id, { active: !user.active }), 'Cuenta actualizada.');
          }
        }}>{user.active ? 'Desactivar' : 'Activar'}</button>
        <button className="secondary" onClick={() => setPasswordFor(user)}>Restablecer contraseña</button></div></td>
      </tr>)}</tbody></table></div>
    <PageControls page={data.value} onOffset={setOffset} />
  </section>;
}

export function Audit() {
  const [offset, setOffset] = useState(0);
  const data = useLoad(() => getAudit(offset, 20), [offset]);
  return <section className="surface stack">
    <h1>Auditoría</h1><LoadNotice {...data} />
    <div className="table-scroll"><table><thead><tr><th>Fecha</th><th>Operación</th><th>Actor</th><th>Objeto</th></tr></thead>
      <tbody>{data.value?.items.map((item) => <tr key={item.id}>
        <td>{formattedDate(item.created_at)}</td><td>{item.action}</td><td>{item.actor_id || item.actor_user_id || 'Sistema'}</td><td>{item.target_id || item.target_user_id || '—'}</td>
      </tr>)}</tbody></table></div>
    <PageControls page={data.value} onOffset={setOffset} />
  </section>;
}

export function System() {
  const data = useLoad(getSystem);
  return <section className="surface stack">
    <div className="section-heading"><h1>Estado del sistema</h1><button className="secondary" onClick={data.reload}>Actualizar</button></div>
    <LoadNotice {...data} />
    {data.value && <dl><dt>API</dt><dd>{data.value.status}</dd><dt>Versión</dt><dd>{data.value.version}</dd></dl>}
  </section>;
}

export function Observability() {
  const data = useLoad(getObservability);
  const payload = data.value;
  const metrics = payload?.observability.metrics;
  return <section className="surface stack">
    <div className="section-heading"><h1>Observabilidad</h1><button className="secondary" onClick={data.reload}>Actualizar</button></div>
    <LoadNotice {...data} />
    {metrics && <div className="cards">{[
      ['Eventos', metrics.total_trace_events], ['Éxito', `${metrics.success_rate_pct}%`],
      ['Latencia P50', `${metrics.p50_latency_ms} ms`], ['Latencia P90', `${metrics.p90_latency_ms} ms`],
      ['Tokens', metrics.total_tokens], ['Costo estimado (USD)', metrics.total_estimated_cost_usd],
    ].map(([label, value]) => <div className="metric surface" key={label}><span>{label}</span><strong>{value}</strong></div>)}</div>}
    {payload && <>
      <h2>Proveedores</h2><ul className="clean-list">{payload.provider_chain.map((item) => <li key={`${item.provider}-${item.model}`}>{item.provider} · {item.model} · {item.configured ? 'Configurado' : 'Pendiente de configuración'}</li>)}</ul>
      <h2>Circuit breakers</h2><div className="table-scroll"><table><thead><tr><th>Proveedor</th><th>Modelo</th><th>Estado</th><th>Fallos</th></tr></thead>
        <tbody>{payload.circuit_breakers.map((item, index) => <tr key={`${item.provider}-${item.model}-${index}`}><td>{item.provider}</td><td>{item.model}</td><td>{item.state}</td><td>{item.failures}</td></tr>)}</tbody>
      </table></div>
      <h2>Trazas recientes</h2><div className="table-scroll"><table><thead><tr><th>Fecha</th><th>Operación</th><th>Proveedor</th><th>Duración</th><th>Resultado</th></tr></thead>
        <tbody>{payload.observability.recent_traces.map((item) => <tr key={item.id}><td>{formattedDate(item.created_at)}</td><td>{item.operation}</td><td>{item.provider}</td><td>{item.latency_ms} ms</td><td>{item.success ? 'Correcto' : item.error_code || 'Fallido'}</td></tr>)}</tbody>
      </table></div>
    </>}
  </section>;
}

export function Queue() {
  const data = useLoad(getQueue);
  const queue = data.value;
  const labels: Record<string, string> = { QUEUED: 'En cola', PROCESSING: 'En ejecución', RETRY_SCHEDULED: 'Reintento programado', COMPLETED: 'Completados', DEAD_LETTER: 'Fallidos', CANCELLED: 'Cancelados' };
  return <section className="surface stack">
    <div className="section-heading"><h1>Cola de procesamiento</h1><button className="secondary" onClick={data.reload}>Actualizar</button></div>
    <LoadNotice {...data} />
    {queue && <><p>Worker: {queue.worker_available ? 'Disponible' : 'Sin actividad reciente'}</p>
      <p>Espera más antigua: {queue.oldest_pending_seconds === null ? 'Sin trabajo pendiente' : `${queue.oldest_pending_seconds} s`}</p>
      <dl className="stat-list">{Object.entries(labels).map(([key, label]) => <div key={key}><dt>{label}</dt><dd>{queue.counts[key] ?? 0}</dd></div>)}</dl>
    </>}
  </section>;
}

export function DeadLetters() {
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [busy, setBusy] = useState(false);
  const attemptKeys = useRef<Record<string, string>>({});
  const data = useLoad(() => getDeadLetters(offset, 20), [offset]);
  return <section className="surface stack">
    <h1>Trabajos fallidos</h1><LoadNotice {...data} />
    {error && <p role="alert">{error}</p>}{success && <p role="status">{success}</p>}
    {data.value?.items.length === 0 && <p>No hay trabajos fallidos en esta página.</p>}
    <div className="table-scroll"><table><thead><tr><th>Radicado</th><th>Intentos</th><th>Motivo</th><th>Fecha</th><th>Acciones</th></tr></thead>
      <tbody>{data.value?.items.map((job) => <tr key={job.id}>
        <td>{job.tracking_code}</td><td>{job.attempts}/{job.max_attempts}</td><td>{job.last_error || '—'}</td><td>{formattedDate(job.finished_at)}</td>
        <td><button className="secondary" disabled={busy} onClick={async () => {
          if (!window.confirm(`¿Reencolar el análisis de ${job.tracking_code}?`)) return;
          setBusy(true);
          setError('');
          setSuccess('');
          const key = attemptKeys.current[job.id] ??= crypto.randomUUID();
          try {
            await requeue(job.id, key);
            delete attemptKeys.current[job.id];
            setSuccess('Reencolado solicitado.');
            data.reload();
          } catch (reason) { setError((reason as Error).message); }
          finally { setBusy(false); }
        }}>Reencolar análisis</button></td>
      </tr>)}</tbody></table></div>
    <div className="actions">
      <button className="secondary" disabled={!offset} onClick={() => setOffset(Math.max(0, offset - 20))}>Anterior</button>
      <button className="secondary" disabled={data.value?.items.length !== 20} onClick={() => setOffset(offset + 20)}>Siguiente</button>
    </div>
  </section>;
}

export function Settings() {
  const data = useLoad(getObservability);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  return <section className="surface stack">
    <h1>Configuración operativa</h1>
    <h2>Simulación de fallos</h2>
    <p>Elige un modo y realiza una consulta nueva o radica un reporte sintético. Los fallos aparecen en Observabilidad aunque el otro proveedor responda correctamente.</p>
    <LoadNotice {...data} />
    {data.value && <form className="stack" onSubmit={async (event) => {
      event.preventDefault();
      const mode = String(new FormData(event.currentTarget).get('mode'));
      if (!window.confirm('¿Aplicar este modo de simulación a CIVIA?')) return;
      setBusy(true);
      setError('');
      try { await setFault(mode); data.reload(); }
      catch (reason) { setError((reason as Error).message); }
      finally { setBusy(false); }
    }}>
      <p>Modo activo: <strong>{data.value.effective_fault_mode}</strong></p>
      <p>Caída total bloquea ambos proveedores. Fallo de respaldo prueba primero Groq. Los demás modos de fallo se aplican al proveedor principal.</p>
      <label>Nuevo modo<select name="mode" defaultValue={data.value.effective_fault_mode}>
        {[['NONE','Desactivada'],['429','Límite de solicitudes'],['503','Servicio no disponible'],['TIMEOUT','Tiempo de espera'],['INVALID_JSON','JSON inválido'],['GROQ_FAIL','Fallo de respaldo'],['TOTAL','Caída total']].map(([mode, label]) => <option key={mode} value={mode}>{label}</option>)}
      </select></label>
      {error && <p role="alert">{error}</p>}<button disabled={busy}>Aplicar simulación</button>
    </form>}
  </section>;
}
