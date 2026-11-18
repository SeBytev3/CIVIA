import { useState } from 'react';
import { decideApproval, getApprovals, getEvents, getInternalNotes, getNotifications, getReportByCode, getReports, getStats, markAllRead, markRead, updateCaseStatus, updateManagement } from '../api';
import type { ReportItem } from '../types';
import { CaliMap } from '../components/CaliMap';
import { LoadNotice, PageControls, useLoad } from '../components/Common';
import { AnalysisState, categories, formattedDate, ReportDetail, statuses } from '../components/ReportDetail';

function LabelStats({ heading, counts, labels }: { heading: string; counts: Record<string, number>; labels?: Record<string, string> }) {
  return <section className="surface"><h2>{heading}</h2>
    {Object.keys(counts).length ? <dl className="stat-list">{Object.entries(counts).map(([key, value]) => <div key={key}><dt>{labels?.[key] || key}</dt><dd>{value}</dd></div>)}</dl> : <p>Sin datos registrados.</p>}
  </section>;
}

export function Dashboard() {
  const data = useLoad(() => Promise.all([getStats(), getApprovals()]));
  const stats = data.value?.[0];
  return <div className="stack"><h1>Dashboard operativo</h1><LoadNotice {...data} />
    {stats && <>
      <div className="cards">
        {[
          ['Reportes', stats.total_reports],
          ['Recibidos', stats.by_status.PENDING_ANALYSIS ?? 0],
          ['En revisión', stats.by_status.IN_REVIEW ?? 0],
          ['Resueltos', stats.by_status.RESOLVED ?? 0],
          ['Rechazados', stats.by_status.REJECTED ?? 0],
          ['Aprobaciones pendientes', data.value?.[1].total ?? 0],
        ].map(([label, value]) => <div className="surface metric" key={label}><span>{label}</span><strong>{value}</strong></div>)}
      </div>
      <div className="cards">
        <LabelStats heading="Categorías" counts={stats.by_category} labels={categories} />
        <LabelStats heading="Comunas" counts={stats.by_comuna} />
        {stats.by_assignee && <LabelStats heading="Responsables" counts={stats.by_assignee} />}
      </div>
    </>}
  </div>;
}

function CaseDetail({ report, onUpdate, onClose }: { report: ReportItem; onUpdate: (report: ReportItem) => void; onClose: () => void }) {
  const data = useLoad(() => getInternalNotes(report.id), [report.id]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState('');
  return <div className="stack">
    <ReportDetail report={report} onClose={onClose} />
    <section className="surface stack">
      <h2>Gestión del caso</h2>
      <form className="stack" onSubmit={async (event) => {
        event.preventDefault();
        setBusy(true);
        setSaved('');
        setError('');
        const formElement = event.currentTarget;
        const form = new FormData(formElement);
        try {
          onUpdate(await updateManagement(report.id, {
            assigned_to: String(form.get('assignee')).trim() || undefined,
            admin_review_status: String(form.get('review')),
            public_note: String(form.get('publicNote')).trim() || undefined,
            internal_note: String(form.get('privateNote')).trim() || undefined,
          }));
          (formElement.elements.namedItem('privateNote') as HTMLTextAreaElement).value = '';
          (formElement.elements.namedItem('publicNote') as HTMLTextAreaElement).value = '';
          data.reload();
          setSaved('Gestión guardada.');
        } catch (reason) { setError((reason as Error).message); }
        finally { setBusy(false); }
      }}>
        <label>Responsable<input name="assignee" defaultValue={report.assigned_to ?? ''} maxLength={120} /></label>
        <label>Revisión administrativa<select name="review" defaultValue={report.admin_review_status || 'PENDING_REVIEW'}>
          <option value="PENDING_REVIEW">Pendiente</option><option value="IN_REVIEW">En revisión</option><option value="REVIEWED">Revisado</option>
        </select></label>
        <label>Nota pública<textarea name="publicNote" maxLength={500} /></label>
        <label>Nota privada<textarea name="privateNote" maxLength={1000} /></label>
        <button disabled={busy}>Guardar gestión</button>
      </form>
      <form className="stack" onSubmit={async (event) => {
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        const status = String(form.get('status'));
        if (!window.confirm(`¿Cambiar el estado a «${statuses[status as keyof typeof statuses]}»?`)) return;
        setBusy(true);
        setError('');
        setSaved('');
        try { onUpdate(await updateCaseStatus(report.id, status, String(form.get('note')))); setSaved('Estado guardado.'); }
        catch (reason) { setError((reason as Error).message); }
        finally { setBusy(false); }
      }}>
        <label>Nuevo estado del reporte<select name="status" required defaultValue="">
          <option disabled value="">Seleccionar</option>
          {(['CONFIRMED', 'IN_REVIEW', 'RESOLVED', 'REJECTED'] as const).map((status) => <option key={status} value={status}>{statuses[status]}</option>)}
        </select></label>
        <label>Mensaje público del cambio<textarea name="note" maxLength={500} /></label>
        <button className="secondary" disabled={busy}>Cambiar estado</button>
      </form>
      {error && <p role="alert">{error}</p>}{saved && <p role="status">{saved}</p>}
    </section>
    <section className="surface"><h2>Notas privadas</h2><LoadNotice {...data} />
      {data.value?.items.length === 0 && <p>No hay notas.</p>}
      <ul className="clean-list">{data.value?.items.map((item, index) => <li key={`${item.created_at}-${index}`}><time>{formattedDate(item.created_at)}</time><p>{item.note}</p></li>)}</ul>
    </section>
  </div>;
}

export function Cases({ map }: { map?: boolean }) {
  const [offset, setOffset] = useState(0);
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [selected, setSelected] = useState<ReportItem | null>(null);
  const data = useLoad(() => getReports({ ...filters, limit: map ? 100 : 20, offset }), [filters, offset, map]);
  if (selected) return <CaseDetail report={selected} onUpdate={setSelected} onClose={() => { setSelected(null); data.reload(); }} />;
  return <section className="surface stack">
    <h1>{map ? 'Mapa de casos' : 'Bandeja de casos'}</h1>
    <form className="actions" onSubmit={(event) => {
      event.preventDefault();
      const fields = new FormData(event.currentTarget);
      setOffset(0);
      setFilters(Object.fromEntries([...fields.entries()].map(([key, value]) => [key, String(value)])));
    }}>
      <label>Buscar<input name="q" placeholder="Título, descripción o radicado" maxLength={100} /></label>
      <label>Estado<select name="status"><option value="">Todos</option>
        {Object.entries(statuses).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
      <label>Categoría<select name="category"><option value="">Todas</option>
        {Object.entries(categories).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
      <label>Comuna<input name="comuna" maxLength={64} /></label>
      <button>Filtrar</button>
    </form>
    <LoadNotice {...data} />
    {data.value?.items.length === 0 && <p>No hay casos para los filtros seleccionados.</p>}
    {map ? <CaliMap reports={data.value?.items || []} onSelectReport={setSelected} height="530px" /> :
      <div className="table-scroll"><table>
        <thead><tr><th>Radicado</th><th>Reporte</th><th>Comuna</th><th>Responsable</th><th>Estado</th><th>Análisis</th></tr></thead>
        <tbody>{data.value?.items.map((item) => <tr key={item.id}>
          <td><button className="table-link" onClick={() => setSelected(item)}>{item.tracking_code}</button></td>
          <td>{item.title}{item.is_synthetic && <small> · Demo sintética</small>}</td><td>{item.comuna || '—'}</td><td>{item.assigned_to || 'Sin asignar'}</td>
          <td>{statuses[item.status]}</td><td><AnalysisState report={item} /></td>
        </tr>)}</tbody>
      </table></div>}
    <PageControls page={data.value} onOffset={setOffset} />
  </section>;
}

export function Notifications() {
  const data = useLoad(getNotifications);
  const [selected, setSelected] = useState<ReportItem | null>(null);
  const [error, setError] = useState('');
  if (selected) return <CaseDetail report={selected} onUpdate={setSelected} onClose={() => { setSelected(null); data.reload(); }} />;
  return <section className="surface stack">
    <div className="section-heading"><h1>Notificaciones</h1><button className="secondary" onClick={async () => {
      try { setError(''); await markAllRead(); data.reload(); }
      catch (reason) { setError((reason as Error).message); }
    }}>Marcar todas como leídas</button></div>
    <LoadNotice {...data} />
    {error && <p role="alert">{error}</p>}
    {data.value && <p>{data.value.unread_total} sin leer</p>}
    <ul className="clean-list">{data.value?.items.map((item) => <li key={item.id} className="notification-row">
      <time>{formattedDate(item.created_at)}</time>
      <p><strong>{item.title}</strong> {item.message}</p>
      <div className="actions"><button className="secondary" onClick={async () => {
        try { setError(''); setSelected(await getReportByCode(item.tracking_code)); }
        catch (reason) { setError((reason as Error).message); }
      }}>Abrir {item.tracking_code}</button>
      {!item.is_read && <button className="secondary" onClick={async () => {
        try { setError(''); await markRead(item.id); data.reload(); }
        catch (reason) { setError((reason as Error).message); }
      }}>Marcar como leída</button>}</div>
    </li>)}</ul>
  </section>;
}

export function Approvals() {
  const [status, setStatus] = useState('PENDING');
  const [offset, setOffset] = useState(0);
  const data = useLoad(() => getApprovals(status, 20, offset), [status, offset]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  return <section className="surface stack">
    <h1>Aprobaciones</h1>
    <label>Filtro<select value={status} onChange={(event) => { setStatus(event.target.value); setOffset(0); }}><option value="PENDING">Pendientes</option><option value="APPROVED">Aprobadas</option><option value="REJECTED">Rechazadas</option><option value="EXPIRED">Vencidas</option></select></label>
    <LoadNotice {...data} />
    {error && <p role="alert">{error}</p>}
    {data.value?.items.length === 0 && <p>No hay solicitudes para este filtro.</p>}
    <ul className="clean-list">{data.value?.items.map((item) => <li key={item.id} className="notification-row">
      <strong>{item.title} · {item.tracking_code}</strong><p>{item.reason}</p>
      {item.proposed_payload.proposed_status && <p>Estado propuesto: {statuses[item.proposed_payload.proposed_status as keyof typeof statuses] || item.proposed_payload.proposed_status}</p>}
      {item.status === 'PENDING' && <div className="actions">{[true, false].map((approve) => <button className={approve ? '' : 'secondary'} key={String(approve)} disabled={busy} onClick={async () => {
        if (!window.confirm(approve ? '¿Aprobar la solicitud y aplicar el cambio propuesto?' : '¿Rechazar la solicitud?')) return;
        setBusy(true);
        setError('');
        try { await decideApproval(item.id, approve); data.reload(); }
        catch (reason) { setError((reason as Error).message); }
        finally { setBusy(false); }
      }}>{approve ? 'Aprobar' : 'Rechazar'}</button>)}</div>}
    </li>)}</ul>
    <PageControls page={data.value} onOffset={setOffset} />
  </section>;
}

export function History() {
  const [events, setEvents] = useState<Awaited<ReturnType<typeof getEvents>>>();
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  return <section className="surface stack">
    <h1>Historial de casos</h1>
    <form className="actions" onSubmit={async (event) => {
      event.preventDefault();
      setError('');
      setEvents(undefined);
      setBusy(true);
      const code = String(new FormData(event.currentTarget).get('code'));
      try { setEvents(await getEvents((await getReportByCode(code)).id)); }
      catch (reason) { setError((reason as Error).message); }
      finally { setBusy(false); }
    }}><label>Radicado<input name="code" required maxLength={60} /></label><button disabled={busy}>Consultar historial</button></form>
    {error && <p role="alert">{error}</p>}
    {events?.length === 0 && <p>El caso aún no tiene eventos.</p>}
    <ol className="timeline">{events?.map((event) => <li key={event.id}><time>{formattedDate(event.created_at)}</time><p>{event.public_message}</p></li>)}</ol>
  </section>;
}
