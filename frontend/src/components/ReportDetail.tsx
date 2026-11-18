import { useEffect, useState } from 'react';
import { confirmReport, getEvidence, getEvents } from '../api';
import type { ReportCategory, ReportEventItem, ReportItem, ReportSeverity, ReportStatus } from '../types';

export const statuses: Record<ReportStatus, string> = {
  PENDING_ANALYSIS: 'Recibido',
  ANALYZED_PENDING_CONFIRMATION: 'Por confirmar',
  CONFIRMED: 'Confirmado',
  IN_REVIEW: 'En revisión',
  RESOLVED: 'Resuelto',
  REJECTED: 'Rechazado',
};
export const categories: Record<ReportCategory, string> = {
  HUECO: 'Huecos viales', BASURAS: 'Basuras y escombros', TALA: 'Tala arbórea',
  QUEMA: 'Quemas e incendios', OTRO: 'Otros',
};
export const severities: Record<ReportSeverity, string> = {
  BAJA: 'Baja', MEDIA: 'Media', ALTA: 'Alta', CRITICA: 'Crítica',
};

export function formattedDate(value: string | null | undefined) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString('es-CO');
}

export function AnalysisState({ report, detailed }: { report: ReportItem; detailed?: boolean }) {
  const label = {
    PENDING: 'Análisis pendiente',
    PROCESSING: 'Analizando reporte',
    AVAILABLE: 'Análisis disponible',
    MANUAL_REVIEW: 'Pendiente de revisión manual',
  }[report.analysis_status ?? (report.ai_category ? 'AVAILABLE' : 'PENDING')];
  return <>
    <span className="status-label">{label}</span>
    {detailed && report.analysis_delayed && <p>En este momento, el servicio de análisis no está disponible. Tu reporte está guardado y será procesado automáticamente cuando el servicio se restablezca. No necesitas enviarlo nuevamente.</p>}
  </>;
}

export function Evidence({ id, kind }: { id: string; kind: 'photo' | 'audio' }) {
  const [url, setUrl] = useState('');
  const [error, setError] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    let objectUrl = '';
    setUrl('');
    setError(false);
    getEvidence(id, kind, controller.signal).then((blob) => {
      if (controller.signal.aborted) return;
      const trustedType = kind === 'photo'
        ? ['image/jpeg', 'image/png', 'image/webp'].includes(blob.type)
        : ['audio/webm', 'audio/ogg', 'audio/wav', 'audio/mpeg', 'audio/mp4'].includes(blob.type);
      if (!trustedType) {
        setError(true);
        return;
      }
      objectUrl = URL.createObjectURL(blob);
      setUrl(objectUrl);
    }).catch(() => { if (!controller.signal.aborted) setError(true); });
    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [id, kind]);
  if (error) return <p>{kind === 'photo' ? 'Foto no disponible.' : 'Audio no disponible.'}</p>;
  if (!url) return <p role="status">Cargando evidencia…</p>;
  return kind === 'photo' ? <img className="evidence" src={url} alt="Evidencia fotográfica del reporte" /> : <audio controls src={url} />;
}

export function ReportDetail({ report, editable, onUpdate, onClose }: {
  report: ReportItem;
  editable?: boolean;
  onUpdate?: (report: ReportItem) => void;
  onClose: () => void;
}) {
  const [events, setEvents] = useState<ReportEventItem[] | null>(null);
  const [historyError, setHistoryError] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let cancelled = false;
    setHistoryError(false);
    setEvents(null);
    getEvents(report.id).then((rows) => {
      if (!cancelled) setEvents(rows);
    }).catch(() => { if (!cancelled) setHistoryError(true); });
    return () => { cancelled = true; };
  }, [report.id, report.updated_at]);

  return <section className="surface stack">
    <div className="section-heading"><h2>{report.title}</h2><button className="secondary" onClick={onClose}>Volver</button></div>
    <strong className="tracking-code">{report.tracking_code}</strong>
    <div className="actions"><span className="status-label">{statuses[report.status]}</span><AnalysisState report={report} detailed /></div>
    <p>{report.description}</p>
    <p>{[report.neighborhood, report.comuna, report.address_hint].filter(Boolean).join(' · ') || 'Ubicación registrada en el mapa'}</p>
    <Evidence id={report.id} kind="photo" />
    {report.has_audio && <Evidence id={report.id} kind="audio" />}
    {report.audio_transcript && <p>Transcripción de la nota de voz: {report.audio_transcript}</p>}
    {(report.ai_summary || report.effective_category) && <section>
      <h3>Diagnóstico</h3>
      <p>{[report.effective_category && categories[report.effective_category], report.effective_severity && severities[report.effective_severity]].filter(Boolean).join(' · ')}</p>
      <p>{report.ai_summary}</p>
    </section>}
    {editable && report.status === 'ANALYZED_PENDING_CONFIRMATION' && <form className="stack" key={report.id} onSubmit={async (event) => {
      event.preventDefault();
      setError('');
      setBusy(true);
      const data = new FormData(event.currentTarget);
      try {
        const severity = data.get('severity') as ReportSeverity | '';
        onUpdate?.(await confirmReport(report.id, data.get('category') as ReportCategory, severity || null, String(data.get('note'))));
      } catch (reason) { setError((reason as Error).message); }
      finally { setBusy(false); }
    }}>
      <h3>Confirmar o corregir la clasificación</h3>
      <label>Categoría<select name="category" defaultValue={report.effective_category || 'OTRO'}>
        {Object.entries(categories).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
      </select></label>
      <label>Severidad<select name="severity" defaultValue={report.effective_severity || ''}>
        <option value="">Sin especificar</option>
        {Object.entries(severities).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
      </select></label>
      <label>Nota opcional<textarea name="note" maxLength={500} /></label>
      {error && <p role="alert">{error}</p>}
      <button disabled={busy}>Guardar clasificación</button>
    </form>}
    <section><h3>Historial</h3>
      {historyError ? <p role="alert">No se pudo cargar el historial.</p> : !events ? <p role="status">Cargando historial…</p> : events.length
        ? <ol className="timeline">{events.map((item) => <li key={item.id}><time>{formattedDate(item.created_at)}</time><p>{item.public_message}</p></li>)}</ol>
        : <p>Este reporte aún no tiene eventos.</p>}
    </section>
  </section>;
}
