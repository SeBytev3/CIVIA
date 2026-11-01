import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  confirmReportClassification,
  decideAdminApproval,
  fetchAdminApprovals,
  fetchAdminObservability,
  fetchReportByCode,
  fetchReports,
  fetchStats,
  queryAgent,
  setAdminFaultInjection,
  submitCitizenReport,
  triggerReportAnalysis,
} from './api';
import { CaliMap } from './components/CaliMap';
import type {
  AgentQueryResponse,
  ObservabilityData,
  PendingApprovalItem,
  ReportCategory,
  ReportItem,
  ReportSeverity,
  ReportStats,
} from './types';

type ActiveTab = 'explorar' | 'reportar' | 'seguimiento' | 'asistente' | 'admin';

const STATUS_LABELS: Record<string, string> = {
  PENDING_ANALYSIS: 'Pendiente de análisis IA',
  ANALYZED_PENDING_CONFIRMATION: 'Analizado · Pendiente confirmar',
  CONFIRMED: 'Confirmado por ciudadano',
  IN_REVIEW: 'En revisión operativa',
  RESOLVED: 'Resuelto',
  REJECTED: 'Descartado',
};

const CALI_PRESETS = [
  { label: 'Av. Sexta · Santa Mónica (Comuna 2)', lat: 3.4658, lon: -76.5283, comuna: 'Comuna 2', neighborhood: 'Santa Mónica' },
  { label: 'Parque del Perro · San Fernando (Comuna 19)', lat: 3.4342, lon: -76.5439, comuna: 'Comuna 19', neighborhood: 'San Fernando' },
  { label: 'Mariano Ramos (Comuna 16)', lat: 3.4012, lon: -76.5045, comuna: 'Comuna 16', neighborhood: 'Mariano Ramos' },
  { label: 'Ecoparque Pance (Comuna 22)', lat: 3.3385, lon: -76.541, comuna: 'Comuna 22', neighborhood: 'Pance' },
  { label: 'Cerro de las Tres Cruces (Comuna 2)', lat: 3.4752, lon: -76.5468, comuna: 'Comuna 2', neighborhood: 'Tres Cruces' },
];

function createCanvasDemoPhoto(category: ReportCategory): Promise<File> {
  return new Promise((resolve) => {
    const canvas = document.createElement('canvas');
    canvas.width = 320;
    canvas.height = 220;
    const ctx = canvas.getContext('2d')!;

    ctx.fillStyle = '#e9f0ef';
    ctx.fillRect(0, 0, 320, 220);

    if (category === 'HUECO') {
      ctx.fillStyle = '#4f545c';
      ctx.fillRect(0, 40, 320, 150);
      ctx.fillStyle = '#f5d042';
      ctx.fillRect(20, 110, 60, 8);
      ctx.fillRect(240, 110, 60, 8);
      ctx.fillStyle = '#1b1d21';
      ctx.beginPath();
      ctx.ellipse(160, 118, 65, 38, 0, 0, Math.PI * 2);
      ctx.fill();
    } else if (category === 'BASURAS') {
      ctx.fillStyle = '#9aa5a8';
      ctx.fillRect(0, 120, 320, 70);
      ctx.fillStyle = '#242b2e';
      ctx.beginPath();
      ctx.arc(120, 130, 36, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = '#2d6a4f';
      ctx.beginPath();
      ctx.arc(175, 125, 40, 0, Math.PI * 2);
      ctx.fill();
    } else if (category === 'TALA') {
      ctx.fillStyle = '#74c69d';
      ctx.fillRect(0, 100, 320, 90);
      ctx.fillStyle = '#6c4628';
      ctx.fillRect(80, 95, 45, 65);
      ctx.fillRect(140, 130, 120, 28);
    } else {
      ctx.fillStyle = '#6b5e53';
      ctx.fillRect(0, 120, 320, 70);
      ctx.fillStyle = '#e63946';
      ctx.beginPath();
      ctx.moveTo(110, 150);
      ctx.lineTo(155, 55);
      ctx.lineTo(205, 150);
      ctx.closePath();
      ctx.fill();
    }

    ctx.fillStyle = '#0f4c5c';
    ctx.fillRect(0, 0, 320, 32);
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 13px sans-serif';
    ctx.fillText(`EVIDENCIA SINTETICA DEMO: ${category}`, 12, 21);

    canvas.toBlob((blob) => {
      const file = new File([blob!], `evidencia_sintetica_${category.toLowerCase()}.png`, {
        type: 'image/png',
      });
      resolve(file);
    }, 'image/png');
  });
}

export function App() {
  const [activeTab, setActiveTab] = useState<ActiveTab>('explorar');
  const [stats, setStats] = useState<ReportStats | null>(null);
  const [reports, setReports] = useState<ReportItem[]>([]);
  const [totalReports, setTotalReports] = useState<number>(0);
  const [loadingReports, setLoadingReports] = useState<boolean>(false);
  const [globalError, setGlobalError] = useState<string | null>(null);
  const [globalSuccess, setGlobalSuccess] = useState<string | null>(null);

  // Filtros en pestaña Explorar
  const [filterCategory, setFilterCategory] = useState<string>('');
  const [filterSeverity, setFilterSeverity] = useState<string>('');
  const [filterStatus, setFilterStatus] = useState<string>('');
  const [filterComuna, setFilterComuna] = useState<string>('');
  const [filterQuery, setFilterQuery] = useState<string>('');
  const [useRadiusFilter, setUseRadiusFilter] = useState<boolean>(false);
  const [radiusKm, setRadiusKm] = useState<number>(3.0);

  // Reporte seleccionado para ver/confirmar
  const [selectedReport, setSelectedReport] = useState<ReportItem | null>(null);
  const [confirmCat, setConfirmCat] = useState<ReportCategory>('HUECO');
  const [confirmSev, setConfirmSev] = useState<ReportSeverity>('ALTA');
  const [confirmNote, setConfirmNote] = useState<string>('');
  const [confirmBusy, setConfirmBusy] = useState<boolean>(false);

  // Formulario de Nuevo Reporte
  const [formCategoryHint, setFormCategoryHint] = useState<ReportCategory>('HUECO');
  const [formTitle, setFormTitle] = useState<string>('');
  const [formDescription, setFormDescription] = useState<string>('');
  const [formLat, setFormLat] = useState<number>(3.4516);
  const [formLon, setFormLon] = useState<number>(-76.532);
  const [formComuna, setFormComuna] = useState<string>('Comuna 2');
  const [formNeighborhood, setFormNeighborhood] = useState<string>('');
  const [formAddress, setFormAddress] = useState<string>('');
  const [formPhoto, setFormPhoto] = useState<File | null>(null);
  const [formPhotoPreview, setFormPhotoPreview] = useState<string | null>(null);
  const [formAudio, setFormAudio] = useState<File | null>(null);
  const [submittingReport, setSubmittingReport] = useState<boolean>(false);
  const [submitLifecycleStep, setSubmitLifecycleStep] = useState<string | null>(null);

  // Grabación opcional de audio (<= 60s)
  const [isRecordingAudio, setIsRecordingAudio] = useState<boolean>(false);
  const [recordingSeconds, setRecordingSeconds] = useState<number>(0);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const recordingTimerRef = useRef<number | null>(null);

  // Seguimiento por radicado
  const [trackingInput, setTrackingInput] = useState<string>('CIV-2026-DEMO0001');
  const [trackedReport, setTrackedReport] = useState<ReportItem | null>(null);
  const [trackingBusy, setTrackingBusy] = useState<boolean>(false);

  // Asistente agéntico
  const [agentInput, setAgentInput] = useState<string>(
    '¿Cuántos reportes de HUECO y QUEMA hay registrados en la Comuna 2 de Cali?'
  );
  const [agentBusy, setAgentBusy] = useState<boolean>(false);
  const [agentResponse, setAgentResponse] = useState<AgentQueryResponse | null>(null);

  // Zona Admin protegida
  const [adminToken, setAdminToken] = useState<string>('civia-admin-demo-2026');
  const [obsData, setObsData] = useState<ObservabilityData | null>(null);
  const [approvals, setApprovals] = useState<PendingApprovalItem[]>([]);
  const [adminBusy, setAdminBusy] = useState<boolean>(false);

  const loadStatsAndReports = useCallback(async () => {
    setLoadingReports(true);
    setGlobalError(null);
    try {
      const [st, repList] = await Promise.all([
        fetchStats(),
        fetchReports({
          category: filterCategory || undefined,
          severity: filterSeverity || undefined,
          status: filterStatus || undefined,
          comuna: filterComuna || undefined,
          q: filterQuery || undefined,
          lat: useRadiusFilter ? formLat : undefined,
          lon: useRadiusFilter ? formLon : undefined,
          radius_km: useRadiusFilter ? radiusKm : undefined,
          limit: 60,
        }),
      ]);
      setStats(st);
      setReports(repList.items);
      setTotalReports(repList.total);
    } catch (err) {
      setGlobalError(err instanceof Error ? err.message : 'Error al cargar datos de CIVIA.');
    } finally {
      setLoadingReports(false);
    }
  }, [
    filterCategory,
    filterSeverity,
    filterStatus,
    filterComuna,
    filterQuery,
    useRadiusFilter,
    formLat,
    formLon,
    radiusKm,
  ]);

  useEffect(() => {
    void loadStatsAndReports();
  }, [loadStatsAndReports]);

  const openReportInspection = (rep: ReportItem) => {
    setSelectedReport(rep);
    setConfirmCat((rep.final_category || rep.ai_category || 'HUECO') as ReportCategory);
    setConfirmSev((rep.final_severity || rep.ai_severity || 'MEDIA') as ReportSeverity);
    setConfirmNote(rep.human_override_note || '');
  };

  const handleCaptureBrowserGps = () => {
    setGlobalError(null);
    if (!navigator.geolocation) {
      setGlobalError(
        'Su navegador no soporta geolocalización automática. Puede seleccionar el punto en el mapa o ingresar las coordenadas manualmente.'
      );
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setFormLat(Number(pos.coords.latitude.toFixed(6)));
        setFormLon(Number(pos.coords.longitude.toFixed(6)));
        setGlobalSuccess('Ubicación GPS capturada correctamente desde su dispositivo.');
      },
      () => {
        setGlobalError(
          'No se concedió permiso de GPS. Puede hacer clic directamente en el mapa de Cali o elegir una ubicación de referencia.'
        );
      },
      { enableHighAccuracy: true, timeout: 8000 }
    );
  };

  const handlePhotoChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0] || null;
    if (!f) return;
    if (f.size > 5 * 1024 * 1024) {
      setGlobalError('La fotografía seleccionada supera el límite máximo de 5 MB.');
      return;
    }
    setFormPhoto(f);
    setFormPhotoPreview(URL.createObjectURL(f));
  };

  const handleGenerateSyntheticPhoto = async () => {
    const file = await createCanvasDemoPhoto(formCategoryHint);
    setFormPhoto(file);
    setFormPhotoPreview(URL.createObjectURL(file));
    if (!formDescription.trim()) {
      const sampleText: Record<ReportCategory, string> = {
        HUECO:
          'DATO SINTÉTICO DEMO: Se reporta hueco profundo en el carril vehicular que dificulta el paso seguro de motocicletas y buses.',
        BASURAS:
          'DATO SINTÉTICO DEMO: Acumulación crítica de bolsas de basura y residuos sólidos sobre el andén peatonal.',
        TALA:
          'DATO SINTÉTICO DEMO: Corte no autorizado de árbol urbano con ramas derribadas en espacio público.',
        QUEMA:
          'DATO SINTÉTICO DEMO: Foco activo de quema de vegetación seca con emisión de humo sobre la ladera.',
        OTRO:
          'DATO SINTÉTICO DEMO: Novedad en infraestructura urbana para verificación técnica municipal.',
      };
      setFormDescription(sampleText[formCategoryHint]);
    }
  };

  const startAudioRecording = async () => {
    setGlobalError(null);
    if (!navigator.mediaDevices?.getUserMedia) {
      setGlobalError('Su navegador no permite grabación directa. Puede adjuntar un archivo de audio (<= 60s / 5MB).');
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      const chunks: BlobPart[] = [];
      recorder.ondataavailable = (ev) => {
        if (ev.data.size > 0) chunks.push(ev.data);
      };
      recorder.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunks, { type: 'audio/webm' });
        const file = new File([blob], 'nota_voz_ciudadana.webm', { type: 'audio/webm' });
        setFormAudio(file);
      };
      recorder.start();
      mediaRecorderRef.current = recorder;
      setIsRecordingAudio(true);
      setRecordingSeconds(0);
      recordingTimerRef.current = window.setInterval(() => {
        setRecordingSeconds((prev) => {
          if (prev >= 59) {
            stopAudioRecording();
            return 60;
          }
          return prev + 1;
        });
      }, 1000);
    } catch {
      setGlobalError('No fue posible acceder al micrófono. Puede adjuntar un archivo de audio opcional.');
    }
  };

  const stopAudioRecording = () => {
    if (recordingTimerRef.current) {
      clearInterval(recordingTimerRef.current);
      recordingTimerRef.current = null;
    }
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop();
    }
    setIsRecordingAudio(false);
  };

  const handleCreateReport = async (e: React.FormEvent) => {
    e.preventDefault();
    setGlobalError(null);
    setGlobalSuccess(null);

    if (!formPhoto) {
      setGlobalError('Por favor adjunte una fotografía de evidencia (o genere una imagen sintética de prueba).');
      return;
    }
    if (formDescription.trim().length < 10) {
      setGlobalError('La descripción debe tener al menos 10 caracteres.');
      return;
    }

    setSubmittingReport(true);
    setSubmitLifecycleStep(
      'Validando archivo e insertando reporte en PostgreSQL; ejecutando análisis multimodal...'
    );

    try {
      const fd = new FormData();
      fd.append('description', formDescription);
      fd.append('latitude', String(formLat));
      fd.append('longitude', String(formLon));
      if (formTitle.trim()) fd.append('title', formTitle.trim());
      if (formComuna.trim()) fd.append('comuna', formComuna.trim());
      if (formNeighborhood.trim()) fd.append('neighborhood', formNeighborhood.trim());
      if (formAddress.trim()) fd.append('address_hint', formAddress.trim());
      fd.append('auto_analyze', 'true');
      fd.append('photo', formPhoto);
      if (formAudio) fd.append('audio', formAudio);

      const created = await submitCitizenReport(fd);
      openReportInspection(created);
      setTrackedReport(created);
      setTrackingInput(created.tracking_code);
      setGlobalSuccess(
        `Reporte registrado con código ${created.tracking_code}. ${created.status_message}`
      );
      await loadStatsAndReports();
    } catch (err) {
      setGlobalError(err instanceof Error ? err.message : 'No fue posible registrar el reporte.');
    } finally {
      setSubmittingReport(false);
      setSubmitLifecycleStep(null);
    }
  };

  const handleConfirmClassification = async (rep: ReportItem) => {
    setConfirmBusy(true);
    setGlobalError(null);
    try {
      const updated = await confirmReportClassification(rep.id, {
        final_category: confirmCat,
        final_severity: confirmSev,
        human_override_note: confirmNote.trim() || undefined,
      });
      setSelectedReport(updated);
      if (trackedReport?.id === updated.id) {
        setTrackedReport(updated);
      }
      setGlobalSuccess(
        `Clasificación confirmada exitosamente para el reporte ${updated.tracking_code} (${updated.final_category} / ${updated.final_severity}).`
      );
      await loadStatsAndReports();
    } catch (err) {
      setGlobalError(err instanceof Error ? err.message : 'No se pudo confirmar la clasificación.');
    } finally {
      setConfirmBusy(false);
    }
  };

  const handleRetryAiAnalysis = async (rep: ReportItem) => {
    setConfirmBusy(true);
    setGlobalError(null);
    try {
      const updated = await triggerReportAnalysis(rep.id);
      openReportInspection(updated);
      if (trackedReport?.id === updated.id) {
        setTrackedReport(updated);
      }
      setGlobalSuccess(`Estado actualizado para ${updated.tracking_code}: ${updated.status_message}`);
      await loadStatsAndReports();
    } catch (err) {
      setGlobalError(err instanceof Error ? err.message : 'No se pudo ejecutar el análisis.');
    } finally {
      setConfirmBusy(false);
    }
  };

  const handleSearchTrackingCode = async (e?: React.FormEvent, customCode?: string) => {
    if (e) e.preventDefault();
    const code = (customCode ?? trackingInput).trim();
    if (!code) return;
    setTrackingBusy(true);
    setGlobalError(null);
    try {
      const rep = await fetchReportByCode(code);
      setTrackedReport(rep);
      openReportInspection(rep);
    } catch (err) {
      setTrackedReport(null);
      setGlobalError(err instanceof Error ? err.message : 'No se encontró el radicado.');
    } finally {
      setTrackingBusy(false);
    }
  };

  const handleRunAgentQuery = async (e?: React.FormEvent, presetQuery?: string) => {
    if (e) e.preventDefault();
    const q = (presetQuery ?? agentInput).trim();
    if (!q) return;
    if (presetQuery) setAgentInput(presetQuery);
    setAgentBusy(true);
    setGlobalError(null);
    try {
      const res = await queryAgent({ query: q });
      setAgentResponse(res);
    } catch (err) {
      setGlobalError(err instanceof Error ? err.message : 'Error al consultar el asistente.');
    } finally {
      setAgentBusy(false);
    }
  };

  const loadAdminPanel = useCallback(async () => {
    setAdminBusy(true);
    setGlobalError(null);
    try {
      const [obs, appList] = await Promise.all([
        fetchAdminObservability(adminToken),
        fetchAdminApprovals(adminToken),
      ]);
      setObsData(obs);
      setApprovals(appList.items);
    } catch (err) {
      setGlobalError(err instanceof Error ? err.message : 'Token administrativo inválido.');
    } finally {
      setAdminBusy(false);
    }
  }, [adminToken]);

  useEffect(() => {
    if (activeTab === 'admin') {
      void loadAdminPanel();
    }
  }, [activeTab, loadAdminPanel]);

  const handleToggleFaultMode = async (mode: string) => {
    setAdminBusy(true);
    setGlobalError(null);
    try {
      await setAdminFaultInjection(adminToken, mode);
      await loadAdminPanel();
      setGlobalSuccess(`Modo de prueba de resiliencia ajustado a: ${mode}`);
    } catch (err) {
      setGlobalError(err instanceof Error ? err.message : 'No se pudo cambiar el modo de falla.');
    } finally {
      setAdminBusy(false);
    }
  };

  const handleApprovalDecision = async (approvalId: string, approve: boolean) => {
    setAdminBusy(true);
    try {
      await decideAdminApproval(adminToken, approvalId, approve, 'Supervisor Cali');
      await loadAdminPanel();
      await loadStatsAndReports();
      setGlobalSuccess(
        approve
          ? 'Solicitud aprobada por humano y aplicada sobre el reporte en PostgreSQL.'
          : 'Solicitud rechazada por el operador humano.'
      );
    } catch (err) {
      setGlobalError(err instanceof Error ? err.message : 'Error al procesar aprobación.');
    } finally {
      setAdminBusy(false);
    }
  };

  const renderStatusTimeline = (status: string) => {
    const steps = [
      { key: 'RECIBIDO', label: '1. Evidencia recibida', done: true },
      {
        key: 'ANALIZADO',
        label: '2. Análisis multimodal IA',
        done: status !== 'PENDING_ANALYSIS',
      },
      {
        key: 'CONFIRMADO',
        label: '3. Confirmación humana',
        done: ['CONFIRMED', 'IN_REVIEW', 'RESOLVED'].includes(status),
      },
      {
        key: 'GESTION',
        label: '4. Gestión / Resolución',
        done: ['IN_REVIEW', 'RESOLVED'].includes(status),
      },
    ];
    return (
      <div className="civia-timeline" role="list" aria-label="Progreso del estado del reporte">
        {steps.map((st) => (
          <div key={st.key} className={`civia-step ${st.done ? 'done' : ''}`} role="listitem">
            {st.done ? '✓ ' : '○ '}
            {st.label}
          </div>
        ))}
      </div>
    );
  };

  const renderInspectionPanel = (rep: ReportItem) => (
    <div className="civia-panel" style={{ borderLeft: '5px solid var(--civia-teal)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '1rem' }}>
        <div>
          <div className="civia-badge-row" style={{ marginBottom: '0.35rem' }}>
            <span className="civia-badge status">{rep.tracking_code}</span>
            <span className="civia-badge status">{STATUS_LABELS[rep.status] || rep.status}</span>
            {rep.is_synthetic && (
              <span className="civia-badge synthetic">DATO SINTÉTICO DEMO (NO PRIVADO)</span>
            )}
          </div>
          <h2 style={{ marginBottom: '0.25rem' }}>{rep.title}</h2>
        </div>
        <button
          type="button"
          className="civia-btn secondary"
          onClick={() => setSelectedReport(null)}
        >
          Cerrar detalle
        </button>
      </div>

      {renderStatusTimeline(rep.status)}

      <p style={{ margin: '0.5rem 0', color: 'var(--civia-muted)', fontWeight: 600 }}>
        {rep.status_message}
      </p>

      <div className="civia-two-col" style={{ marginTop: '1rem' }}>
        <div>
          <img
            src={rep.photo_url}
            alt={`Evidencia fotográfica del reporte ${rep.tracking_code}`}
            style={{ width: '100%', maxHeight: '280px', objectFit: 'cover', borderRadius: '10px' }}
          />
          <p style={{ marginTop: '0.65rem' }}>{rep.description}</p>
          <p style={{ fontSize: '0.85rem', color: 'var(--civia-muted)' }}>
            <strong>Coordenadas GPS:</strong> ({rep.latitude}, {rep.longitude}) ·{' '}
            <strong>Ubicación:</strong> {rep.comuna || 'Cali'} — {rep.neighborhood || rep.address_hint || 'Sin dirección adicional'}
          </p>
          {rep.audio_transcript && (
            <p style={{ fontSize: '0.85rem', background: '#f0f5f4', padding: '0.6rem', borderRadius: '8px' }}>
              <strong>Transcripción de nota de voz:</strong> {rep.audio_transcript}
            </p>
          )}
        </div>

        <div style={{ background: '#f6faf9', padding: '1rem', borderRadius: '10px', border: '1px solid var(--civia-border)' }}>
          <h3 style={{ marginTop: 0, fontSize: '1.05rem', color: 'var(--civia-teal-dark)' }}>
            Diagnóstico Sugerido por IA vs. Clasificación Ciudadana
          </h3>

          {rep.ai_category ? (
            <div style={{ marginBottom: '1rem', fontSize: '0.9rem' }}>
              <div>
                <strong>Categoría sugerida por IA:</strong>{' '}
                <span className={`civia-badge cat-${rep.ai_category}`}>{rep.ai_category}</span> ·{' '}
                <strong>Severidad sugerida:</strong> {rep.ai_severity} (Confianza:{' '}
                {rep.ai_confidence !== null ? `${Math.round(rep.ai_confidence * 100)}%` : 'N/A'})
              </div>
              <p style={{ margin: '0.45rem 0', background: '#fff', padding: '0.65rem', borderRadius: '8px', border: '1px solid #dce4e2' }}>
                {rep.ai_summary}
              </p>
            </div>
          ) : (
            <div className="civia-alert info">
              El análisis automático de IA está pendiente (`PENDING_ANALYSIS`). El reporte ya se encuentra guardado de forma segura en PostgreSQL; puede confirmar la categoría manualmente o solicitar el análisis ahora.
              <div style={{ marginTop: '0.5rem' }}>
                <button
                  type="button"
                  className="civia-btn secondary"
                  disabled={confirmBusy}
                  onClick={() => void handleRetryAiAnalysis(rep)}
                >
                  {confirmBusy ? 'Analizando evidencia...' : 'Ejecutar análisis multimodal IA ahora'}
                </button>
              </div>
            </div>
          )}

          <div style={{ borderTop: '1px solid var(--civia-border)', paddingTop: '0.85rem' }}>
            <div style={{ marginBottom: '0.5rem', fontSize: '0.9rem' }}>
              <strong>Estado de confirmación humana:</strong>{' '}
              {rep.human_confirmed ? (
                <span style={{ color: 'var(--civia-forest)', fontWeight: 700 }}>
                  ✓ Confirmado ({rep.final_category} / {rep.final_severity})
                </span>
              ) : (
                <span style={{ color: 'var(--civia-amber)', fontWeight: 700 }}>
                  Pendiente de revisión/confirmación del ciudadano
                </span>
              )}
            </div>

            <div className="civia-filter-bar" style={{ gridTemplateColumns: '1fr 1fr', marginBottom: '0.6rem' }}>
              <div className="civia-field">
                <label htmlFor="confirm-cat">Categoría definitiva (editable)</label>
                <select
                  id="confirm-cat"
                  value={confirmCat}
                  onChange={(e) => setConfirmCat(e.target.value as ReportCategory)}
                >
                  <option value="HUECO">HUECO (Deterioro vial)</option>
                  <option value="BASURAS">BASURAS (Residuos sólidos)</option>
                  <option value="TALA">TALA (Afectación arbórea)</option>
                  <option value="QUEMA">QUEMA (Incendio / Humo)</option>
                  <option value="OTRO">OTRO (Fuera de categoría)</option>
                </select>
              </div>
              <div className="civia-field">
                <label htmlFor="confirm-sev">Severidad confirmada</label>
                <select
                  id="confirm-sev"
                  value={confirmSev}
                  onChange={(e) => setConfirmSev(e.target.value as ReportSeverity)}
                >
                  <option value="BAJA">BAJA</option>
                  <option value="MEDIA">MEDIA</option>
                  <option value="ALTA">ALTA</option>
                  <option value="CRITICA">CRITICA</option>
                </select>
              </div>
            </div>

            <div className="civia-field" style={{ marginBottom: '0.75rem' }}>
              <label htmlFor="confirm-note">Nota ciudadana o corrección (opcional)</label>
              <input
                id="confirm-note"
                type="text"
                placeholder="Ej. Confirmo el diagnóstico o corrijo porque es quema de basuras..."
                value={confirmNote}
                onChange={(e) => setConfirmNote(e.target.value)}
              />
            </div>

            <button
              type="button"
              className="civia-btn accent"
              disabled={confirmBusy}
              onClick={() => void handleConfirmClassification(rep)}
            >
              {confirmBusy
                ? 'Guardando confirmación en PostgreSQL...'
                : rep.human_confirmed
                ? 'Actualizar clasificación confirmada'
                : 'Confirmar clasificación ciudadana'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );

  return (
    <div>
      <header className="civia-header">
        <div className="civia-header-inner">
          <div className="civia-brand">
            <div className="civia-logo-badge" aria-hidden="true">
              CV
            </div>
            <div>
              <h1>CIVIA · Cali y Valle del Cauca</h1>
              <p>Reportes ciudadanos viales y ambientales asistidos por IA con confirmación humana</p>
            </div>
          </div>

          <nav className="civia-nav" aria-label="Navegación principal de CIVIA">
            <button
              type="button"
              className={`civia-nav-btn ${activeTab === 'explorar' ? 'active' : ''}`}
              onClick={() => setActiveTab('explorar')}
            >
              Mapa y Reportes
            </button>
            <button
              type="button"
              className={`civia-nav-btn ${activeTab === 'reportar' ? 'active' : ''}`}
              onClick={() => setActiveTab('reportar')}
            >
              + Nuevo Reporte
            </button>
            <button
              type="button"
              className={`civia-nav-btn ${activeTab === 'seguimiento' ? 'active' : ''}`}
              onClick={() => setActiveTab('seguimiento')}
            >
              Seguimiento Radicado
            </button>
            <button
              type="button"
              className={`civia-nav-btn ${activeTab === 'asistente' ? 'active' : ''}`}
              onClick={() => setActiveTab('asistente')}
            >
              Asistente Agéntico
            </button>
            <button
              type="button"
              className={`civia-nav-btn ${activeTab === 'admin' ? 'active' : ''}`}
              onClick={() => setActiveTab('admin')}
            >
              Observabilidad Admin
            </button>
          </nav>
        </div>
      </header>

      <main className="civia-container">
        {globalError && (
          <div className="civia-alert error" role="alert">
            {globalError}
          </div>
        )}
        {globalSuccess && (
          <div className="civia-alert success" role="status">
            {globalSuccess}
          </div>
        )}

        {/* Estadísticas reales desde PostgreSQL */}
        {stats && (
          <section className="civia-stats-grid" aria-label="Estadísticas reales en PostgreSQL">
            <div className="civia-stat-card">
              <div className="civia-stat-label">Total Reportes BD</div>
              <div className="civia-stat-value">{stats.total_reports}</div>
              <div className="civia-stat-sub">Almacenados en PostgreSQL</div>
            </div>
            <div className="civia-stat-card">
              <div className="civia-stat-label">Huecos Viales</div>
              <div className="civia-stat-value">{stats.by_category.HUECO || 0}</div>
              <div className="civia-stat-sub">Categoría HUECO</div>
            </div>
            <div className="civia-stat-card">
              <div className="civia-stat-label">Puntos de Basura</div>
              <div className="civia-stat-value">{stats.by_category.BASURAS || 0}</div>
              <div className="civia-stat-sub">Categoría BASURAS</div>
            </div>
            <div className="civia-stat-card">
              <div className="civia-stat-label">Tala y Arbolado</div>
              <div className="civia-stat-value">{stats.by_category.TALA || 0}</div>
              <div className="civia-stat-sub">Categoría TALA</div>
            </div>
            <div className="civia-stat-card">
              <div className="civia-stat-label">Quemas / Incendios</div>
              <div className="civia-stat-value">{stats.by_category.QUEMA || 0}</div>
              <div className="civia-stat-sub">Categoría QUEMA</div>
            </div>
            <div className="civia-stat-card">
              <div className="civia-stat-label">Confirmados / Gestión</div>
              <div className="civia-stat-value">
                {(stats.by_status.CONFIRMED || 0) +
                  (stats.by_status.IN_REVIEW || 0) +
                  (stats.by_status.RESOLVED || 0)}
              </div>
              <div className="civia-stat-sub">Verificados por humanos</div>
            </div>
          </section>
        )}

        {selectedReport && renderInspectionPanel(selectedReport)}

        {/* PESTAÑA 1: EXPLORAR MAPA Y REPORTES */}
        {activeTab === 'explorar' && (
          <>
            <section className="civia-panel">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem', marginBottom: '0.75rem' }}>
                <h2>Mapa Interactivo de Santiago de Cali ({totalReports} reportes encontrados)</h2>
                <button
                  type="button"
                  className="civia-btn secondary"
                  onClick={() => void loadStatsAndReports()}
                  disabled={loadingReports}
                >
                  {loadingReports ? 'Actualizando...' : 'Actualizar datos'}
                </button>
              </div>

              <div className="civia-filter-bar">
                <div className="civia-field">
                  <label htmlFor="flt-cat">Categoría</label>
                  <select
                    id="flt-cat"
                    value={filterCategory}
                    onChange={(e) => setFilterCategory(e.target.value)}
                  >
                    <option value="">Todas las categorías</option>
                    <option value="HUECO">HUECO</option>
                    <option value="BASURAS">BASURAS</option>
                    <option value="TALA">TALA</option>
                    <option value="QUEMA">QUEMA</option>
                    <option value="OTRO">OTRO</option>
                  </select>
                </div>

                <div className="civia-field">
                  <label htmlFor="flt-sev">Severidad</label>
                  <select
                    id="flt-sev"
                    value={filterSeverity}
                    onChange={(e) => setFilterSeverity(e.target.value)}
                  >
                    <option value="">Todas</option>
                    <option value="CRITICA">CRITICA</option>
                    <option value="ALTA">ALTA</option>
                    <option value="MEDIA">MEDIA</option>
                    <option value="BAJA">BAJA</option>
                  </select>
                </div>

                <div className="civia-field">
                  <label htmlFor="flt-status">Estado</label>
                  <select
                    id="flt-status"
                    value={filterStatus}
                    onChange={(e) => setFilterStatus(e.target.value)}
                  >
                    <option value="">Todos los estados</option>
                    <option value="PENDING_ANALYSIS">Pendiente análisis IA</option>
                    <option value="ANALYZED_PENDING_CONFIRMATION">Analizado (Por confirmar)</option>
                    <option value="CONFIRMED">Confirmado</option>
                    <option value="IN_REVIEW">En revisión</option>
                    <option value="RESOLVED">Resuelto</option>
                  </select>
                </div>

                <div className="civia-field">
                  <label htmlFor="flt-comuna">Comuna</label>
                  <input
                    id="flt-comuna"
                    type="text"
                    placeholder="Ej. Comuna 2, Comuna 16"
                    value={filterComuna}
                    onChange={(e) => setFilterComuna(e.target.value)}
                  />
                </div>

                <div className="civia-field">
                  <label htmlFor="flt-q">Búsqueda por texto o código</label>
                  <input
                    id="flt-q"
                    type="text"
                    placeholder="Barrio, vía o CIV-2026..."
                    value={filterQuery}
                    onChange={(e) => setFilterQuery(e.target.value)}
                  />
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap', marginBottom: '0.85rem', fontSize: '0.86rem' }}>
                <label style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', fontWeight: 600 }}>
                  <input
                    type="checkbox"
                    checked={useRadiusFilter}
                    onChange={(e) => setUseRadiusFilter(e.target.checked)}
                  />
                  Filtrar por radio geográfico Haversine desde ({formLat}, {formLon})
                </label>
                {useRadiusFilter && (
                  <label style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem' }}>
                    Radio (km):
                    <input
                      type="number"
                      min="0.5"
                      max="50"
                      step="0.5"
                      value={radiusKm}
                      onChange={(e) => setRadiusKm(Number(e.target.value) || 2)}
                      style={{ width: '75px', padding: '0.3rem' }}
                    />
                  </label>
                )}
              </div>

              <CaliMap
                reports={reports}
                onSelectReport={(rep) => openReportInspection(rep)}
                selectable={useRadiusFilter}
                selectedLat={formLat}
                selectedLon={formLon}
                onPickCoords={(lat, lon) => {
                  setFormLat(lat);
                  setFormLon(lon);
                }}
              />
            </section>

            <section aria-label="Listado de reportes ciudadanos">
              <div className="civia-reports-grid">
                {reports.map((rep) => (
                  <article key={rep.id} className="civia-report-card">
                    <img
                      className="civia-report-thumb"
                      src={rep.photo_url}
                      alt={rep.title}
                      loading="lazy"
                    />
                    <div className="civia-report-body">
                      <div className="civia-badge-row">
                        <span className="civia-badge status">{rep.tracking_code}</span>
                        {rep.effective_category && (
                          <span className={`civia-badge cat-${rep.effective_category}`}>
                            {rep.effective_category}
                          </span>
                        )}
                        {rep.is_synthetic && (
                          <span className="civia-badge synthetic">DEMO SINTÉTICO</span>
                        )}
                      </div>
                      <h3 style={{ margin: '0.2rem 0', fontSize: '1.02rem' }}>{rep.title}</h3>
                      <p style={{ margin: 0, fontSize: '0.86rem', color: 'var(--civia-muted)', flex: 1 }}>
                        {rep.description.slice(0, 125)}
                        {rep.description.length > 125 ? '...' : ''}
                      </p>
                      <div style={{ fontSize: '0.8rem', color: 'var(--civia-muted)' }}>
                        <strong>Estado:</strong> {STATUS_LABELS[rep.status] || rep.status} ·{' '}
                        <strong>{rep.comuna || 'Cali'}</strong>
                        {rep.distance_km !== null ? ` · a ${rep.distance_km} km` : ''}
                      </div>
                      <button
                        type="button"
                        className="civia-btn secondary"
                        style={{ marginTop: '0.4rem' }}
                        onClick={() => openReportInspection(rep)}
                      >
                        Revisar análisis IA / Confirmar
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            </section>
          </>
        )}

        {/* PESTAÑA 2: NUEVO REPORTE CIUDADANO */}
        {activeTab === 'reportar' && (
          <section className="civia-panel">
            <h2>Registrar Nuevo Reporte Ciudadano en Cali / Valle del Cauca</h2>
            <p style={{ color: 'var(--civia-muted)', marginTop: 0 }}>
              Flujo vertical completo: captura de evidencia y GPS → almacenamiento seguro en PostgreSQL → análisis multimodal asistido por IA → confirmación o corrección humana.
            </p>

            <form onSubmit={(e) => void handleCreateReport(e)}>
              <div className="civia-two-col">
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
                  <div className="civia-filter-bar" style={{ gridTemplateColumns: '1fr 1fr', marginBottom: 0 }}>
                    <div className="civia-field">
                      <label htmlFor="rep-cat-hint">Tipo de incidente observado</label>
                      <select
                        id="rep-cat-hint"
                        value={formCategoryHint}
                        onChange={(e) => setFormCategoryHint(e.target.value as ReportCategory)}
                      >
                        <option value="HUECO">HUECO (Bache o daño vial)</option>
                        <option value="BASURAS">BASURAS (Acumulación de residuos)</option>
                        <option value="TALA">TALA (Afectación de árboles)</option>
                        <option value="QUEMA">QUEMA (Incendio o quema abierta)</option>
                        <option value="OTRO">OTRO</option>
                      </select>
                    </div>
                    <div className="civia-field">
                      <label htmlFor="rep-comuna">Comuna o Corregimiento</label>
                      <input
                        id="rep-comuna"
                        type="text"
                        value={formComuna}
                        onChange={(e) => setFormComuna(e.target.value)}
                        placeholder="Ej. Comuna 2, Comuna 19, Pance"
                      />
                    </div>
                  </div>

                  <div className="civia-field">
                    <label htmlFor="rep-title">Título breve del reporte (opcional)</label>
                    <input
                      id="rep-title"
                      type="text"
                      value={formTitle}
                      onChange={(e) => setFormTitle(e.target.value)}
                      placeholder="Ej. Hueco profundo en carril derecho de Avenida Sexta"
                    />
                  </div>

                  <div className="civia-field">
                    <label htmlFor="rep-desc">Descripción detallada del incidente *</label>
                    <textarea
                      id="rep-desc"
                      rows={3}
                      required
                      value={formDescription}
                      onChange={(e) => setFormDescription(e.target.value)}
                      placeholder="Describa el problema observado (mínimo 10 caracteres). No incluya datos personales sensibles."
                    />
                  </div>

                  <div className="civia-filter-bar" style={{ gridTemplateColumns: '1fr 1fr', marginBottom: 0 }}>
                    <div className="civia-field">
                      <label htmlFor="rep-barrio">Barrio</label>
                      <input
                        id="rep-barrio"
                        type="text"
                        value={formNeighborhood}
                        onChange={(e) => setFormNeighborhood(e.target.value)}
                        placeholder="Ej. Granada, San Fernando"
                      />
                    </div>
                    <div className="civia-field">
                      <label htmlFor="rep-addr">Dirección o punto de referencia</label>
                      <input
                        id="rep-addr"
                        type="text"
                        value={formAddress}
                        onChange={(e) => setFormAddress(e.target.value)}
                        placeholder="Ej. Calle 5 con Carrera 34"
                      />
                    </div>
                  </div>

                  {/* Fotografía obligatoria */}
                  <div style={{ background: '#f5f9f8', padding: '0.9rem', borderRadius: '10px', border: '1px solid var(--civia-border)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem', marginBottom: '0.5rem' }}>
                      <label htmlFor="rep-photo" style={{ fontWeight: 700, fontSize: '0.9rem' }}>
                        Fotografía de evidencia * (JPEG, PNG o WEBP, máx. 5 MB)
                      </label>
                      <button
                        type="button"
                        className="civia-btn secondary"
                        onClick={() => void handleGenerateSyntheticPhoto()}
                      >
                        Generar foto sintética de prueba ({formCategoryHint})
                      </button>
                    </div>
                    <input
                      id="rep-photo"
                      type="file"
                      accept="image/jpeg,image/png,image/webp"
                      onChange={handlePhotoChange}
                    />
                    {formPhotoPreview && (
                      <div style={{ marginTop: '0.65rem' }}>
                        <img
                          src={formPhotoPreview}
                          alt="Vista previa de evidencia"
                          style={{ maxHeight: '150px', borderRadius: '8px', border: '1px solid #ccc' }}
                        />
                      </div>
                    )}
                  </div>

                  {/* Nota de voz opcional */}
                  <div style={{ background: '#f5f9f8', padding: '0.9rem', borderRadius: '10px', border: '1px solid var(--civia-border)' }}>
                    <div style={{ fontWeight: 700, fontSize: '0.88rem', marginBottom: '0.4rem' }}>
                      Nota de voz opcional (máximo 60 segundos y 5 MB)
                    </div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.6rem', alignItems: 'center' }}>
                      {!isRecordingAudio ? (
                        <button
                          type="button"
                          className="civia-btn secondary"
                          onClick={() => void startAudioRecording()}
                        >
                          Grabar audio con micrófono
                        </button>
                      ) : (
                        <button
                          type="button"
                          className="civia-btn accent"
                          onClick={stopAudioRecording}
                        >
                          Detener grabación ({recordingSeconds}s / 60s)
                        </button>
                      )}
                      <input
                        type="file"
                        accept="audio/wav,audio/mpeg,audio/ogg,audio/webm"
                        aria-label="Cargar archivo de audio opcional"
                        onChange={(e) => setFormAudio(e.target.files?.[0] || null)}
                      />
                    </div>
                    {formAudio && (
                      <div style={{ fontSize: '0.8rem', marginTop: '0.35rem', color: 'var(--civia-teal)' }}>
                        Audio adjunto: {formAudio.name} ({Math.round(formAudio.size / 1024)} KB)
                      </div>
                    )}
                  </div>
                </div>

                {/* Columna derecha: Captura GPS y selección en mapa */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
                    <strong>Localización Geográfica (GPS o clic en el mapa)</strong>
                    <button
                      type="button"
                      className="civia-btn secondary"
                      onClick={handleCaptureBrowserGps}
                    >
                      Usar mi ubicación GPS
                    </button>
                  </div>

                  <div className="civia-field">
                    <label htmlFor="cali-preset">O elegir punto de referencia en Cali:</label>
                    <select
                      id="cali-preset"
                      onChange={(e) => {
                        const idx = Number(e.target.value);
                        const p = CALI_PRESETS[idx];
                        if (p) {
                          setFormLat(p.lat);
                          setFormLon(p.lon);
                          setFormComuna(p.comuna);
                          setFormNeighborhood(p.neighborhood);
                        }
                      }}
                    >
                      <option value="">-- Seleccionar ubicación rápida en Cali --</option>
                      {CALI_PRESETS.map((p, idx) => (
                        <option key={p.label} value={idx}>
                          {p.label}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div className="civia-filter-bar" style={{ gridTemplateColumns: '1fr 1fr', marginBottom: 0 }}>
                    <div className="civia-field">
                      <label htmlFor="rep-lat">Latitud *</label>
                      <input
                        id="rep-lat"
                        type="number"
                        step="0.000001"
                        required
                        value={formLat}
                        onChange={(e) => setFormLat(Number(e.target.value))}
                      />
                    </div>
                    <div className="civia-field">
                      <label htmlFor="rep-lon">Longitud *</label>
                      <input
                        id="rep-lon"
                        type="number"
                        step="0.000001"
                        required
                        value={formLon}
                        onChange={(e) => setFormLon(Number(e.target.value))}
                      />
                    </div>
                  </div>

                  <CaliMap
                    reports={reports}
                    selectable={true}
                    selectedLat={formLat}
                    selectedLon={formLon}
                    height="300px"
                    onPickCoords={(lat, lon) => {
                      setFormLat(lat);
                      setFormLon(lon);
                    }}
                  />
                </div>
              </div>

              {submitLifecycleStep && (
                <div className="civia-alert info" style={{ marginTop: '1rem' }} role="status">
                  {submitLifecycleStep}
                </div>
              )}

              <div style={{ marginTop: '1.1rem', display: 'flex', gap: '0.8rem' }}>
                <button type="submit" className="civia-btn accent" disabled={submittingReport}>
                  {submittingReport
                    ? 'Procesando reporte y evidencia...'
                    : 'Enviar Reporte y Analizar Evidencia con IA'}
                </button>
              </div>
            </form>
          </section>
        )}

        {/* PESTAÑA 3: SEGUIMIENTO POR RADICADO */}
        {activeTab === 'seguimiento' && (
          <section className="civia-panel">
            <h2>Seguimiento de Reporte mediante Código de Radicado</h2>
            <p style={{ color: 'var(--civia-muted)', marginTop: 0 }}>
              Consulte el estado real en PostgreSQL, el diagnóstico sugerido por IA y la confirmación ciudadana ingresando su código `CIV-2026-...`.
            </p>

            <form
              onSubmit={(e) => void handleSearchTrackingCode(e)}
              style={{ display: 'flex', gap: '0.65rem', flexWrap: 'wrap', marginBottom: '1rem' }}
            >
              <input
                type="text"
                aria-label="Código de radicado"
                value={trackingInput}
                onChange={(e) => setTrackingInput(e.target.value)}
                placeholder="Ej. CIV-2026-DEMO0001"
                style={{ padding: '0.65rem 0.85rem', borderRadius: '8px', border: '1px solid #bfd0cd', minWidth: '250px' }}
              />
              <button type="submit" className="civia-btn" disabled={trackingBusy}>
                {trackingBusy ? 'Consultando BD...' : 'Consultar Radicado'}
              </button>
            </form>

            <div style={{ display: 'flex', gap: '0.45rem', flexWrap: 'wrap', marginBottom: '1rem' }}>
              <span style={{ fontSize: '0.82rem', color: 'var(--civia-muted)', alignSelf: 'center' }}>
                Radicados sintéticos de prueba rápida:
              </span>
              {['CIV-2026-DEMO0001', 'CIV-2026-DEMO0002', 'CIV-2026-DEMO0004', 'CIV-2026-DEMO0008'].map(
                (code) => (
                  <button
                    key={code}
                    type="button"
                    className="civia-btn secondary"
                    style={{ padding: '0.35rem 0.7rem', fontSize: '0.8rem' }}
                    onClick={() => {
                      setTrackingInput(code);
                      void handleSearchTrackingCode(undefined, code);
                    }}
                  >
                    {code}
                  </button>
                )
              )}
            </div>

            {trackedReport && !selectedReport && renderInspectionPanel(trackedReport)}
          </section>
        )}

        {/* PESTAÑA 4: ASISTENTE AGÉNTICO CON HERRAMIENTAS Y 4 LÍMITES */}
        {activeTab === 'asistente' && (
          <section className="civia-panel">
            <h2>Asistente Agéntico de Consulta y Gestión (SQL Directo + Herramientas Tipadas)</h2>
            <p style={{ color: 'var(--civia-muted)', marginTop: 0 }}>
              El agente consulta PostgreSQL mediante herramientas tipadas (`consultar_reportes`, `obtener_reporte`, `clasificar_evidencia`, `proponer_actualizacion_critica`) bajo cuatro límites estrictos: vueltas máximas, presupuesto de tokens, timeout por herramienta y aprobación humana obligatoria para escrituras.
            </p>

            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.45rem', marginBottom: '0.85rem' }}>
              {[
                '¿Cuántos reportes de HUECO y QUEMA hay registrados en la Comuna 2 de Cali?',
                'Dame el detalle completo del radicado CIV-2026-DEMO0004 en el Cerro de las Tres Cruces.',
                '¿Cuántos reportes de radiación nuclear o cruce satelital NDVI hay en la Comuna 99?',
                'Propón cambiar el estado del reporte CIV-2026-DEMO0002 a RESOLVED porque ya se recolectó la basura.',
              ].map((q) => (
                <button
                  key={q}
                  type="button"
                  className="civia-btn secondary"
                  style={{ fontSize: '0.78rem', padding: '0.4rem 0.7rem' }}
                  onClick={() => void handleRunAgentQuery(undefined, q)}
                >
                  {q}
                </button>
              ))}
            </div>

            <form
              onSubmit={(e) => void handleRunAgentQuery(e)}
              style={{ display: 'flex', gap: '0.65rem', flexWrap: 'wrap', marginBottom: '1.1rem' }}
            >
              <input
                type="text"
                aria-label="Consulta para el agente de CIVIA"
                value={agentInput}
                onChange={(e) => setAgentInput(e.target.value)}
                style={{ flex: 1, minWidth: '260px', padding: '0.65rem 0.85rem', borderRadius: '8px', border: '1px solid #bfd0cd' }}
              />
              <button type="submit" className="civia-btn" disabled={agentBusy}>
                {agentBusy ? 'Ejecutando agente y herramientas...' : 'Consultar al Agente'}
              </button>
            </form>

            {agentResponse && (
              <div style={{ background: '#f5f9f8', padding: '1.1rem', borderRadius: '10px', border: '1px solid var(--civia-border)' }}>
                <div className="civia-badge-row" style={{ marginBottom: '0.65rem' }}>
                  <span className="civia-badge status">
                    Vueltas: {agentResponse.iterations_used} / {agentResponse.max_iterations}
                  </span>
                  <span className="civia-badge status">
                    Tokens: {agentResponse.total_tokens_used} / {agentResponse.max_tokens_budget}
                  </span>
                  <span className="civia-badge status">Latencia: {agentResponse.latency_ms} ms</span>
                  {agentResponse.guardrail_triggered && (
                    <span className="civia-badge synthetic">
                      Límite activado: {agentResponse.guardrail_triggered}
                    </span>
                  )}
                </div>

                <div style={{ background: '#ffffff', padding: '0.9rem', borderRadius: '8px', border: '1px solid #dce4e2', marginBottom: '0.85rem', whiteSpace: 'pre-wrap' }}>
                  <strong>Respuesta del Agente:</strong>
                  <p style={{ margin: '0.4rem 0 0' }}>{agentResponse.answer}</p>
                </div>

                {agentResponse.requires_human_approval && (
                  <div className="civia-alert info">
                    <strong>Guardrail #4 activo (Aprobación Humana Obligatoria):</strong> La IA no modificó directamente la tabla de reportes. Se registró la solicitud pendiente #{agentResponse.pending_approval_id?.slice(0, 8)} en la bandeja de Observabilidad Admin.
                  </div>
                )}

                <div>
                  <strong style={{ fontSize: '0.88rem' }}>
                    Herramientas tipadas invocadas ({agentResponse.tools_invoked.length}):
                  </strong>
                  {agentResponse.tools_invoked.map((t, idx) => (
                    <pre
                      key={`${t.tool}-${idx}`}
                      style={{
                        background: '#14242b',
                        color: '#e2f1ef',
                        padding: '0.65rem',
                        borderRadius: '8px',
                        fontSize: '0.78rem',
                        overflowX: 'auto',
                        marginTop: '0.4rem',
                      }}
                    >
                      {`Herramienta: ${t.tool}(${JSON.stringify(t.args)})\nResultado SQL/Acción: ${JSON.stringify(t.result, null, 2)}`}
                    </pre>
                  ))}
                </div>
              </div>
            )}
          </section>
        )}

        {/* PESTAÑA 5: ZONA ADMIN Y OBSERVABILIDAD PROTEGIDA */}
        {activeTab === 'admin' && (
          <section className="civia-panel">
            <h2>Zona Protegida de Observabilidad Técnica, Resiliencia y Aprobaciones Humanas</h2>
            <p style={{ color: 'var(--civia-muted)', marginTop: 0 }}>
              Exclusivo para evaluación técnica y operadores autorizados. Las trazas internas, nombres de proveedores, latencias P50/P90 y fallos jamás se exponen en la vista ciudadana.
            </p>

            <div style={{ display: 'flex', gap: '0.6rem', alignItems: 'center', flexWrap: 'wrap', marginBottom: '1rem' }}>
              <label htmlFor="admin-token-input" style={{ fontWeight: 600, fontSize: '0.86rem' }}>
                X-Admin-Token:
              </label>
              <input
                id="admin-token-input"
                type="password"
                value={adminToken}
                onChange={(e) => setAdminToken(e.target.value)}
                style={{ padding: '0.5rem 0.75rem', borderRadius: '8px', border: '1px solid #bfd0cd' }}
              />
              <button
                type="button"
                className="civia-btn"
                onClick={() => void loadAdminPanel()}
                disabled={adminBusy}
              >
                {adminBusy ? 'Cargando...' : 'Refrescar Observabilidad'}
              </button>
            </div>

            {obsData && (
              <>
                <div style={{ background: '#f5f9f8', padding: '1rem', borderRadius: '10px', border: '1px solid var(--civia-border)', marginBottom: '1rem' }}>
                  <h3 style={{ marginTop: 0, fontSize: '1rem' }}>
                    Simulador de Fallas Controladas (`FALLA_FORZADA` actual: {obsData.effective_fault_mode})
                  </h3>
                  <p style={{ fontSize: '0.84rem', color: 'var(--civia-muted)', marginTop: 0 }}>
                    Permite demostrar en vivo durante la sustentación cómo responde el router Gemini → Groq → Gemini ante fallos reales sin exponer tracebacks al ciudadano:
                  </p>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.45rem' }}>
                    {[
                      { mode: 'NONE', label: 'Normal (NONE)' },
                      { mode: '429', label: 'Forzar 429 en Primario → Fallback Groq' },
                      { mode: '503', label: 'Forzar 503 en Primario → Fallback Groq' },
                      { mode: 'TIMEOUT', label: 'Forzar Timeout en Primario → Fallback Groq' },
                      { mode: 'INVALID_JSON', label: 'Forzar JSON Inválido → Fallback Groq' },
                      { mode: 'GROQ_FAIL', label: 'Falla Primario + Groq → 3er modelo Gemini' },
                      { mode: 'TOTAL', label: 'Caída Total (3 proveedores) → PENDING_ANALYSIS' },
                    ].map((btn) => (
                      <button
                        key={btn.mode}
                        type="button"
                        className={`civia-btn ${obsData.effective_fault_mode === btn.mode ? 'accent' : 'secondary'}`}
                        style={{ fontSize: '0.8rem', padding: '0.45rem 0.75rem' }}
                        onClick={() => void handleToggleFaultMode(btn.mode)}
                      >
                        {btn.label}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Métricas de Latencia P50/P90 y Costo */}
                <div className="civia-stats-grid">
                  <div className="civia-stat-card">
                    <div className="civia-stat-label">Latencia P50 (Éxito)</div>
                    <div className="civia-stat-value">
                      {obsData.observability.metrics.p50_success_latency_ms} ms
                    </div>
                    <div className="civia-stat-sub">
                      Global P50: {obsData.observability.metrics.p50_latency_ms} ms
                    </div>
                  </div>
                  <div className="civia-stat-card">
                    <div className="civia-stat-label">Latencia P90 (Éxito)</div>
                    <div className="civia-stat-value">
                      {obsData.observability.metrics.p90_success_latency_ms} ms
                    </div>
                    <div className="civia-stat-sub">
                      Global P90: {obsData.observability.metrics.p90_latency_ms} ms
                    </div>
                  </div>
                  <div className="civia-stat-card">
                    <div className="civia-stat-label">Eventos de Traza</div>
                    <div className="civia-stat-value">
                      {obsData.observability.metrics.total_trace_events}
                    </div>
                    <div className="civia-stat-sub">
                      Éxito: {obsData.observability.metrics.success_rate_pct}%
                    </div>
                  </div>
                  <div className="civia-stat-card">
                    <div className="civia-stat-label">Tokens Acumulados</div>
                    <div className="civia-stat-value">
                      {obsData.observability.metrics.total_tokens}
                    </div>
                    <div className="civia-stat-sub">Contabilizados en BD</div>
                  </div>
                  <div className="civia-stat-card">
                    <div className="civia-stat-label">Costo Estimado Total</div>
                    <div className="civia-stat-value">
                      ${obsData.observability.metrics.total_estimated_cost_usd.toFixed(5)}
                    </div>
                    <div className="civia-stat-sub">
                      Medio: ${obsData.observability.metrics.avg_cost_per_event_usd.toFixed(6)} USD
                    </div>
                  </div>
                </div>

                {/* Bandeja de aprobaciones humanas pendientes */}
                <div style={{ marginBottom: '1.25rem' }}>
                  <h3>Solicitudes de Escritura Crítica Pendientes de Aprobación Humana ({approvals.length})</h3>
                  {approvals.length === 0 ? (
                    <p style={{ fontSize: '0.86rem', color: 'var(--civia-muted)' }}>
                      No hay solicitudes pendientes. Pida al agente cambiar el estado de un reporte para ver cómo se detiene aquí hasta recibir aprobación humana.
                    </p>
                  ) : (
                    <table className="civia-table">
                      <thead>
                        <tr>
                          <th>Radicado</th>
                          <th>Cambio Propuesto</th>
                          <th>Justificación</th>
                          <th>Estado</th>
                          <th>Acción Humana</th>
                        </tr>
                      </thead>
                      <tbody>
                        {approvals.map((pa) => (
                          <tr key={pa.id}>
                            <td>
                              <strong>{pa.tracking_code}</strong>
                            </td>
                            <td>
                              {pa.proposed_payload.previous_status} →{' '}
                              <strong>{pa.proposed_payload.proposed_status}</strong>
                            </td>
                            <td>{pa.reason}</td>
                            <td>
                              <span className="civia-badge status">{pa.status}</span>
                            </td>
                            <td>
                              {pa.status === 'PENDING' ? (
                                <div style={{ display: 'flex', gap: '0.4rem' }}>
                                  <button
                                    type="button"
                                    className="civia-btn"
                                    style={{ padding: '0.3rem 0.65rem', fontSize: '0.78rem' }}
                                    onClick={() => void handleApprovalDecision(pa.id, true)}
                                  >
                                    Aprobar
                                  </button>
                                  <button
                                    type="button"
                                    className="civia-btn secondary"
                                    style={{ padding: '0.3rem 0.65rem', fontSize: '0.78rem' }}
                                    onClick={() => void handleApprovalDecision(pa.id, false)}
                                  >
                                    Rechazar
                                  </button>
                                </div>
                              ) : (
                                <span>Decidido por {pa.decided_by}</span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>

                {/* Cadena de proveedores y Trazas */}
                <h3>Cadena de Proveedores Configurada y Trazas Recientes (Sanitizadas)</h3>
                <div style={{ overflowX: 'auto' }}>
                  <table className="civia-table">
                    <thead>
                      <tr>
                        <th>Operación</th>
                        <th>Proveedor / Modelo</th>
                        <th>Intento</th>
                        <th>Resultado</th>
                        <th>Latencia</th>
                        <th>Tokens</th>
                        <th>Causa Técnica (Interna)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {obsData.observability.recent_traces.slice(0, 20).map((tr) => (
                        <tr key={tr.id}>
                          <td>{tr.operation}</td>
                          <td>
                            <strong>{tr.provider}</strong> · {tr.model}
                          </td>
                          <td>#{tr.attempt_number}</td>
                          <td>
                            <span
                              className={`civia-badge ${tr.success ? 'cat-TALA' : 'cat-QUEMA'}`}
                            >
                              {tr.success ? 'OK' : 'FALLO → FALLBACK'}
                            </span>
                          </td>
                          <td>{tr.latency_ms} ms</td>
                          <td>{tr.total_tokens}</td>
                          <td>{tr.error_code ? `${tr.error_code}: ${tr.error_detail || ''}` : '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </section>
        )}
      </main>
    </div>
  );
}
