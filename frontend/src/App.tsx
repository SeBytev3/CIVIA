import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  confirmReportClassification,
  decideAdminApproval,
  fetchAdminApprovals,
  fetchAdminNotifications,
  fetchAdminObservability,
  fetchReportByCode,
  
  fetchReports,
  fetchStats,
  getOperationStatus,
  markAdminNotificationRead,
  markAllAdminNotificationsRead,
  queryAgent,
  setAdminFaultInjection,
  submitCitizenReport,
  triggerReportAnalysis,
  updateReportManagement,
} from './api';
import { CaliMap } from './components/CaliMap';
import type {
  AdminNotificationItem,
  AdminNotificationsResponse,
  AgentQueryResponse,
  ObservabilityData,
  OperationStatusResponse,
  PendingApprovalItem,
  ReportCategory,
  ReportEventItem,
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

async function fetchDemoPhoto(category: ReportCategory): Promise<File> {
  const catLower = category.toLowerCase();
  const sampleUrl = `/demo_evidence/sample_${catLower}.jpg`;
  const res = await fetch(sampleUrl);
  if (!res.ok) {
    throw new Error(`Muestra no disponible para ${category} (HTTP ${res.status})`);
  }
  const blob = await res.blob();
  return new File([blob], `evidencia_sintetica_${catLower}.jpg`, { type: 'image/jpeg' });
}

interface AgentQueryAttempt {
  query: string;
  idempotencyKey: string;
  operationToken: string;
  operationId?: string | null;
  operationStatus?: string | null;
  lastResponse?: AgentQueryResponse;
  updatedAt: number;
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
  const [formIsSynthetic, setFormIsSynthetic] = useState<boolean>(false);
  const [formAudio, setFormAudio] = useState<File | null>(null);
  const [submittingReport, setSubmittingReport] = useState<boolean>(false);
  const [submitLifecycleStep, setSubmitLifecycleStep] = useState<string | null>(null);

  // Cámara web y captura de fotografía
  const [isCameraActive, setIsCameraActive] = useState<boolean>(false);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [isDragOver, setIsDragOver] = useState<boolean>(false);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const cameraStreamRef = useRef<MediaStream | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // Grabación opcional de audio (<= 60s)
  const [isRecordingAudio, setIsRecordingAudio] = useState<boolean>(false);
  const [recordingSeconds, setRecordingSeconds] = useState<number>(0);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const recordingTimerRef = useRef<number | null>(null);

  // Seguimiento por radicado
  const [trackingInput, setTrackingInput] = useState<string>('');
  const [trackedReport, setTrackedReport] = useState<ReportItem | null>(null);
  const [trackingBusy, setTrackingBusy] = useState<boolean>(false);

  // Asistente agéntico
  const [activeAttempt, setActiveAttempt] = useState<AgentQueryAttempt | null>(() => {
    try {
      const saved = localStorage.getItem('civia_pwa_agent_attempt');
      if (saved) {
        return JSON.parse(saved) as AgentQueryAttempt;
      }
    } catch {
      // Ignorar fallo de parseo
    }
    return null;
  });
  const [agentInput, setAgentInput] = useState<string>(
    '¿Cuántos reportes de HUECO y QUEMA hay registrados en la Comuna 2 de Cali?'
  );
  const [agentBusy, setAgentBusy] = useState<boolean>(false);
  const [agentResponse, setAgentResponse] = useState<AgentQueryResponse | null>(null);
  const [operationStatus, setOperationStatus] = useState<OperationStatusResponse | null>(null);
  const [checkingOperation, setCheckingOperation] = useState<boolean>(false);

  // Sincronizar estado inicial desde intento previo en localStorage (F4)
  useEffect(() => {
    if (activeAttempt) {
      if (activeAttempt.query) {
        setAgentInput(activeAttempt.query);
      }
      if (activeAttempt.lastResponse) {
        setAgentResponse(activeAttempt.lastResponse);
      }
    }
  }, []);

  // Zona Admin protegida (no hardcodear secretos en el bundle cliente)
  const [adminToken, setAdminToken] = useState<string>('');
  const [obsData, setObsData] = useState<ObservabilityData | null>(null);
  const [approvals, setApprovals] = useState<PendingApprovalItem[]>([]);
  const [adminBusy, setAdminBusy] = useState<boolean>(false);

  // Notificaciones internas y gestión administrativa
  const [adminNotifs, setAdminNotifs] = useState<AdminNotificationsResponse | null>(null);
  const [notifFilter, setNotifFilter] = useState<string>('ALL');
  const [notifUnreadOnly, setNotifUnreadOnly] = useState<boolean>(false);
  const [managementAssignedTo, setManagementAssignedTo] = useState<string>('');
  const [managementReviewStatus, setManagementReviewStatus] = useState<string>('PENDING_REVIEW');
  const [managementPublicNote, setManagementPublicNote] = useState<string>('');
  const [savingManagement, setSavingManagement] = useState<boolean>(false);

  // Estado post-envío y accesibilidad
  const [newlyCreatedReport, setNewlyCreatedReport] = useState<ReportItem | null>(null);
  const [copiedRadicado, setCopiedRadicado] = useState<boolean>(false);
  const successHeadingRef = useRef<HTMLHeadingElement | null>(null);
  const lastFocusedElementRef = useRef<HTMLElement | null>(null);

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

  const handleCopyTrackingCode = async (code: string) => {
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(code);
      } else {
        const ta = document.createElement('textarea');
        ta.value = code;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
      }
      setCopiedRadicado(true);
      setTimeout(() => setCopiedRadicado(false), 2500);
    } catch {
      setCopiedRadicado(false);
    }
  };

  const openReportInspection = (rep: ReportItem, triggerEl?: HTMLElement | null) => {
    lastFocusedElementRef.current = triggerEl || (document.activeElement as HTMLElement | null);
    setSelectedReport(rep);
    setConfirmCat((rep.final_category || rep.ai_category || 'HUECO') as ReportCategory);
    setConfirmSev((rep.final_severity || rep.ai_severity || 'MEDIA') as ReportSeverity);
    setConfirmNote(rep.human_override_note || '');
    setManagementAssignedTo(rep.assigned_to || '');
    setManagementReviewStatus(rep.admin_review_status || 'PENDING_REVIEW');
    setManagementPublicNote('');
  };

  const handleCloseInspection = () => {
    setSelectedReport(null);
    setTrackedReport(null);
    setNewlyCreatedReport(null);
    setTimeout(() => {
      if (lastFocusedElementRef.current && typeof lastFocusedElementRef.current.focus === 'function') {
        lastFocusedElementRef.current.focus();
      }
    }, 50);
  };

  const renderExternalDeliveryNotice = () => (
    <div className="civia-notice-card" role="region" aria-label="Información sobre notificaciones">
      <div className="civia-notice-title">
        <span aria-hidden="true">ℹ️</span> Información sobre notificaciones y entidades responsables
      </div>
      <p className="civia-notice-body">
        Tu reporte fue registrado correctamente en CIVIA y estará disponible para seguimiento con tu número de radicado. Por ahora, el envío de notificaciones por correo electrónico a las entidades responsables no está habilitado. Tu reporte permanecerá guardado en la plataforma para su consulta y gestión.
      </p>
      <div className="civia-notice-status">
        <strong>Estado de entrega externa:</strong> Correo a entidad: No enviado — servicio no habilitado
      </div>
    </div>
  );

  const renderEventsTimeline = (events?: ReportEventItem[]) => {
    if (!events || events.length === 0) {
      return (
        <div style={{ fontSize: '0.85rem', color: 'var(--civia-muted)', padding: '0.4rem 0' }}>
          Reporte registrado en la plataforma. Pendiente de siguientes actuaciones operativas.
        </div>
      );
    }

    const formatEventDate = (dtStr: string) => {
      try {
        const d = new Date(dtStr);
        return d.toLocaleString('es-CO', {
          dateStyle: 'short',
          timeStyle: 'short',
        });
      } catch {
        return dtStr;
      }
    };

    const getActorLabel = (actor: string) => {
      if (actor === 'CITIZEN') return 'Ciudadano';
      if (actor === 'ADMIN') return 'Operador CIVIA';
      return 'Sistema IA';
    };

    return (
      <div className="civia-events-timeline" role="list" aria-label="Historial de eventos del reporte">
        {events.map((ev) => (
          <div key={ev.id} className="civia-event-row" role="listitem">
            <div
              className={`civia-event-node ${ev.actor_type.toLowerCase()}`}
              aria-hidden="true"
            />
            <div className="civia-event-content">
              <div className="civia-event-meta">
                <strong>{getActorLabel(ev.actor_type)}</strong>
                <time dateTime={ev.created_at}>{formatEventDate(ev.created_at)}</time>
              </div>
              <p className="civia-event-msg">{ev.public_message}</p>
            </div>
          </div>
        ))}
      </div>
    );
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

  const stopCamera = useCallback(() => {
    if (cameraStreamRef.current) {
      cameraStreamRef.current.getTracks().forEach((track) => {
        try {
          track.stop();
        } catch {
          // Ignorar fallo al detener pista
        }
      });
      cameraStreamRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    setIsCameraActive(false);
    setCameraError(null);
  }, []);

  // Detener cámara al cambiar de pestaña
  useEffect(() => {
    if (activeTab !== 'reportar') {
      stopCamera();
    }
  }, [activeTab, stopCamera]);

  // Limpieza al desmontar componente
  useEffect(() => {
    return () => {
      stopCamera();
      if (recordingTimerRef.current) {
        clearInterval(recordingTimerRef.current);
      }
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        mediaRecorderRef.current.stop();
      }
    };
  }, [stopCamera]);

  const startCamera = async () => {
    stopCamera();
    setCameraError(null);
    setGlobalError(null);
    if (!navigator.mediaDevices?.getUserMedia) {
      setCameraError(
        'Este navegador o dispositivo no permite acceso directo a la cámara. Utilice la opción de subir fotografía.'
      );
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: { ideal: 'environment' },
          width: { ideal: 1280 },
          height: { ideal: 720 },
        },
        audio: false,
      });
      cameraStreamRef.current = stream;
      setIsCameraActive(true);
    } catch {
      setCameraError(
        'No se concedió acceso a la cámara o el dispositivo está ocupado. Puede subir una fotografía desde sus archivos.'
      );
    }
  };

  useEffect(() => {
    if (isCameraActive && videoRef.current && cameraStreamRef.current) {
      videoRef.current.srcObject = cameraStreamRef.current;
      videoRef.current.play().catch(() => {});
    }
  }, [isCameraActive]);

  const captureCameraFrame = () => {
    if (!videoRef.current) return;
    const v = videoRef.current;
    const canvas = document.createElement('canvas');
    canvas.width = v.videoWidth || 1024;
    canvas.height = v.videoHeight || 768;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.drawImage(v, 0, 0, canvas.width, canvas.height);
    canvas.toBlob(
      (blob) => {
        if (!blob) return;
        const file = new File([blob], `captura_camara_${Date.now()}.jpg`, { type: 'image/jpeg' });
        handleAssignPhoto(file, false);
      },
      'image/jpeg',
      0.92
    );
  };

  const handleAssignPhoto = (file: File, isSynthetic: boolean) => {
    if (file.size > 5 * 1024 * 1024) {
      setGlobalError('La fotografía seleccionada supera el límite máximo de 5 MB.');
      return;
    }
    const allowed = ['image/jpeg', 'image/png', 'image/webp'];
    if (!allowed.includes(file.type)) {
      setGlobalError('Formato de imagen no admitido. Utilice archivos JPEG, PNG o WEBP.');
      return;
    }
    stopCamera();
    setFormPhoto(file);
    setFormPhotoPreview(URL.createObjectURL(file));
    setFormIsSynthetic(isSynthetic);
    setGlobalError(null);
  };

  const handlePhotoChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) {
      handleAssignPhoto(f, false);
    }
  };

  const handleDropPhoto = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f) {
      handleAssignPhoto(f, false);
    }
  };

  const handleSelectSyntheticSample = async (category: ReportCategory) => {
    try {
      const file = await fetchDemoPhoto(category);
      handleAssignPhoto(file, true);
      setFormCategoryHint(category);
      if (!formDescription.trim()) {
        const sampleText: Record<ReportCategory, string> = {
          HUECO:
            'DATO SINTÉTICO DEMO: Se reporta bache profundo en carril vehicular que deteriora la calzada y pone en riesgo a motocicletas.',
          BASURAS:
            'DATO SINTÉTICO DEMO: Acumulación crítica de residuos sólidos y bolsas rotas sobre el andén peatonal.',
          TALA:
            'DATO SINTÉTICO DEMO: Afectación de arbolado urbano con ramas desgajadas bloqueando el paso.',
          QUEMA:
            'DATO SINTÉTICO DEMO: Quema de vegetación y pastizales en lote baldío con emisión de humo.',
          OTRO:
            'DATO SINTÉTICO DEMO: Poste de servicios ladeado con cableado descolgado sobre espacio público.',
        };
        setFormDescription(sampleText[category]);
      }
    } catch (err) {
      console.warn('La muestra sintética de prueba no está disponible:', err);
      setGlobalError('La muestra de prueba no está disponible en este momento. Por favor toma una fotografía con tu cámara o selecciona una imagen desde tu dispositivo.');
      handleDiscardPhoto();
    }
  };

  const handleDiscardPhoto = () => {
    stopCamera();
    setFormPhoto(null);
    setFormPhotoPreview(null);
    setFormIsSynthetic(false);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
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
      'Estamos guardando tu reporte de forma segura y procesando la evidencia fotográfica...'
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
      fd.append('is_synthetic', formIsSynthetic ? 'true' : 'false');
      if (formAudio) fd.append('audio', formAudio);

      const created = await submitCitizenReport(fd);
      if (created.citizen_edit_token) {
        try {
          sessionStorage.setItem(`civia_edit_token_${created.id}`, created.citizen_edit_token);
        } catch {
          // Ignorar si sessionStorage no está disponible
        }
      }
      setNewlyCreatedReport(created);
      setTrackedReport(created);
      setTrackingInput(created.tracking_code);
      setConfirmCat((created.final_category || created.ai_category || 'HUECO') as ReportCategory);
      setConfirmSev((created.final_severity || created.ai_severity || 'MEDIA') as ReportSeverity);
      setConfirmNote(created.human_override_note || '');
      setSelectedReport(null);

      // Limpiar formulario tras éxito confirmado
      handleDiscardPhoto();
      setFormDescription('');
      setFormTitle('');
      setFormNeighborhood('');
      setFormAddress('');
      setFormAudio(null);
      stopCamera();
      stopAudioRecording();

      setActiveTab('seguimiento');
      setGlobalSuccess(
        `¡Tu reporte fue recibido exitosamente con radicado ${created.tracking_code}!`
      );
      await loadStatsAndReports();

      // Scroll accesible y foco al encabezado del resultado
      setTimeout(() => {
        if (successHeadingRef.current) {
          successHeadingRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' });
          successHeadingRef.current.focus();
        }
      }, 100);
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
      let storedEditToken = rep.citizen_edit_token || null;
      if (!storedEditToken) {
        try {
          storedEditToken = sessionStorage.getItem(`civia_edit_token_${rep.id}`);
        } catch {
          storedEditToken = null;
        }
      }
      const updated = await confirmReportClassification(
        rep.id,
        {
          final_category: confirmCat,
          final_severity: confirmSev,
          human_override_note: confirmNote.trim() || undefined,
          edit_token: storedEditToken || undefined,
        },
        storedEditToken,
        adminToken
      );
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
      if (selectedReport?.id === updated.id) {
        setSelectedReport(updated);
      }
      if (trackedReport?.id === updated.id) {
        setTrackedReport(updated);
      }
      setConfirmCat((updated.final_category || updated.ai_category || 'HUECO') as ReportCategory);
      setConfirmSev((updated.final_severity || updated.ai_severity || 'MEDIA') as ReportSeverity);
      setConfirmNote(updated.human_override_note || '');
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
      setConfirmCat((rep.final_category || rep.ai_category || 'HUECO') as ReportCategory);
      setConfirmSev((rep.final_severity || rep.ai_severity || 'MEDIA') as ReportSeverity);
      setConfirmNote(rep.human_override_note || '');
    } catch (err) {
      setTrackedReport(null);
      setGlobalError(err instanceof Error ? err.message : 'No se encontró el radicado.');
    } finally {
      setTrackingBusy(false);
    }
  };

  const handleCheckOperationStatus = async (opId: string, qToken?: string) => {
    setCheckingOperation(true);
    try {
      const res = await getOperationStatus(
        opId,
        qToken || undefined,
        adminToken || undefined
      );
      setOperationStatus(res);
    } catch (err) {
      setGlobalError(err instanceof Error ? err.message : 'Error al consultar estado de la operación.');
    } finally {
      setCheckingOperation(false);
    }
  };

  const handleClearAgentSession = () => {
    try {
      localStorage.removeItem('civia_pwa_agent_attempt');
    } catch {
      // Ignorar fallo de storage
    }
    setActiveAttempt(null);
    setAgentResponse(null);
    setOperationStatus(null);
  };

  const handleRunAgentQuery = async (e?: React.FormEvent, presetQuery?: string) => {
    if (e) e.preventDefault();
    const q = (presetQuery ?? agentInput).trim();
    if (!q) return;
    if (presetQuery) setAgentInput(presetQuery);
    setAgentBusy(true);
    setGlobalError(null);
    setOperationStatus(null);

    // Obtener o reutilizar intento persistente para la misma consulta (F4)
    let currentAttempt: AgentQueryAttempt | null = null;
    try {
      const saved = localStorage.getItem('civia_pwa_agent_attempt');
      if (saved) {
        const parsed = JSON.parse(saved) as AgentQueryAttempt;
        if (parsed.query === q && parsed.idempotencyKey && parsed.operationToken) {
          currentAttempt = parsed;
        }
      }
    } catch {
      // Fallback si localStorage falla
    }

    if (!currentAttempt) {
      const idempKey =
        typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : `idemp-${Date.now()}`;
      const opToken =
        typeof crypto !== 'undefined' && crypto.randomUUID ? `opt-${crypto.randomUUID()}` : `opt-${Date.now()}`;
      currentAttempt = {
        query: q,
        idempotencyKey: idempKey,
        operationToken: opToken,
        updatedAt: Date.now(),
      };
      try {
        localStorage.setItem('civia_pwa_agent_attempt', JSON.stringify(currentAttempt));
      } catch {
        // Fallback
      }
      setActiveAttempt(currentAttempt);
    }

    try {
      const res = await queryAgent({
        query: q,
        idempotency_key: currentAttempt.idempotencyKey,
        operation_token: currentAttempt.operationToken,
      });
      setAgentResponse(res);
      currentAttempt.lastResponse = res;
      if (res.operation_id) {
        currentAttempt.operationId = res.operation_id;
        currentAttempt.operationStatus = res.operation_status;
      }
      currentAttempt.updatedAt = Date.now();
      try {
        localStorage.setItem('civia_pwa_agent_attempt', JSON.stringify(currentAttempt));
      } catch {
        // Fallback
      }
      setActiveAttempt(currentAttempt);
    } catch (err) {
      setGlobalError(err instanceof Error ? err.message : 'Error al consultar el asistente.');
    } finally {
      setAgentBusy(false);
    }
  };

  const loadAdminPanel = useCallback(async () => {
    if (!adminToken.trim()) return;
    setAdminBusy(true);
    setGlobalError(null);
    try {
      const [obs, appList, notifs] = await Promise.all([
        fetchAdminObservability(adminToken),
        fetchAdminApprovals(adminToken),
        fetchAdminNotifications(adminToken, {
          filter_type: notifFilter,
          unread_only: notifUnreadOnly,
          limit: 50,
        }),
      ]);
      setObsData(obs);
      setApprovals(appList.items);
      setAdminNotifs(notifs);
    } catch (err) {
      setGlobalError(err instanceof Error ? err.message : 'Token administrativo inválido.');
    } finally {
      setAdminBusy(false);
    }
  }, [adminToken, notifFilter, notifUnreadOnly]);

  const handleMarkNotifRead = async (notificationId: string) => {
    try {
      await markAdminNotificationRead(adminToken, notificationId);
      await loadAdminPanel();
    } catch (err) {
      setGlobalError(err instanceof Error ? err.message : 'No se pudo actualizar la notificación.');
    }
  };

  const handleMarkAllNotifsRead = async () => {
    try {
      const res = await markAllAdminNotificationsRead(adminToken);
      setGlobalSuccess(`Se marcaron ${res.updated_count} notificaciones como leídas.`);
      await loadAdminPanel();
    } catch (err) {
      setGlobalError(err instanceof Error ? err.message : 'No se pudo completar la operación.');
    }
  };

  const handleSaveManagement = async (reportId: string) => {
    setSavingManagement(true);
    try {
      const updated = await updateReportManagement(adminToken, reportId, {
        assigned_to: managementAssignedTo || undefined,
        admin_review_status: managementReviewStatus || undefined,
        public_note: managementPublicNote || undefined,
      });
      setSelectedReport(updated);
      if (trackedReport?.id === updated.id) {
        setTrackedReport(updated);
      }
      setGlobalSuccess(`Gestión actualizada correctamente para el reporte ${updated.tracking_code}.`);
      setManagementPublicNote('');
      await loadAdminPanel();
      await loadStatsAndReports();
    } catch (err) {
      setGlobalError(err instanceof Error ? err.message : 'Error al guardar la gestión administrativa.');
    } finally {
      setSavingManagement(false);
    }
  };

  useEffect(() => {
    if (activeTab === 'admin' && adminToken.trim().length > 0) {
      void loadAdminPanel();
    }
  }, [activeTab, adminToken, loadAdminPanel]);

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
        label: '2. Diagnóstico del reporte',
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

  const renderInspectionPanel = (rep: ReportItem, onClose?: () => void) => (
    <div className="civia-panel" style={{ borderLeft: '5px solid var(--civia-teal)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '1rem', flexWrap: 'wrap' }}>
        <div>
          <div className="civia-badge-row" style={{ marginBottom: '0.35rem' }}>
            <span className="civia-badge status" style={{ fontFamily: 'monospace', fontWeight: 800 }}>{rep.tracking_code}</span>
            <button
              type="button"
              className="civia-btn secondary sm"
              style={{ minHeight: '26px', padding: '0.15rem 0.5rem', fontSize: '0.75rem' }}
              onClick={() => void handleCopyTrackingCode(rep.tracking_code)}
              aria-label="Copiar número de radicado al portapapeles"
            >
              {copiedRadicado ? '✓ ¡Copiado!' : '📋 Copiar'}
            </button>
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
          onClick={() => {
            if (onClose) {
              onClose();
            } else {
              handleCloseInspection();
            }
          }}
          aria-label="Cerrar detalle de inspección de reporte"
        >
          ✕ Cerrar detalle
        </button>
      </div>

      {renderStatusTimeline(rep.status)}

      <p style={{ margin: '0.5rem 0', color: 'var(--civia-muted)', fontWeight: 600 }}>
        {rep.status_message}
      </p>

      {renderExternalDeliveryNotice()}

      <div className="civia-two-col" style={{ marginTop: '1rem' }}>
        <div>
          <div
            style={{
              backgroundColor: '#0f172a',
              borderRadius: '10px',
              overflow: 'hidden',
              display: 'flex',
              justifyContent: 'center',
              alignItems: 'center',
              minHeight: '220px',
              maxHeight: '340px',
            }}
          >
            <img
              src={rep.photo_url}
              alt={`Evidencia fotográfica del reporte ${rep.tracking_code}`}
              style={{
                width: '100%',
                maxHeight: '340px',
                objectFit: 'contain',
                display: 'block',
              }}
            />
          </div>
          {rep.is_synthetic && (
            <div
              style={{
                background: '#e8f4f8',
                color: '#0f4c5c',
                fontSize: '0.8rem',
                fontWeight: 600,
                padding: '0.35rem 0.65rem',
                borderRadius: '6px',
                marginTop: '0.45rem',
                display: 'inline-block',
                border: '1px solid #b6d4db',
              }}
            >
              ℹ Imagen generada con IA · Simulación
            </div>
          )}
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
                  {confirmBusy ? 'Analizando evidencia...' : 'Solicitar diagnóstico de fotografía'}
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
                ? 'Guardando tu confirmación...'
                : rep.human_confirmed
                ? 'Actualizar clasificación confirmada'
                : 'Confirmar clasificación ciudadana'}
            </button>
          </div>
        </div>
      </div>

      {/* Historial y Trazabilidad Ciudadana */}
      <div style={{ marginTop: '1.25rem', borderTop: '1px solid var(--civia-border)', paddingTop: '1rem' }}>
        <h3 style={{ margin: '0 0 0.5rem 0', fontSize: '1.05rem', color: 'var(--civia-teal-dark)' }}>
          Historial y Trazabilidad Ciudadana
        </h3>
        {renderEventsTimeline(rep.events)}
      </div>

      {/* Panel de Gestión Interna si es Administrador */}
      {adminToken.trim().length > 0 && (
        <div style={{ marginTop: '1.25rem', background: '#f0f7f6', border: '1.5px solid #a3cac4', borderRadius: '10px', padding: '1.1rem' }}>
          <h3 style={{ margin: '0 0 0.4rem 0', fontSize: '1rem', color: 'var(--civia-teal-dark)' }}>
            🛠️ Gestión Interna y Asignación Operativa (Exclusivo Administrador)
          </h3>
          <p style={{ margin: '0 0 0.75rem 0', fontSize: '0.84rem', color: 'var(--civia-muted)' }}>
            Asigne la entidad responsable y agregue notas públicas de avance que serán visibles en la línea de tiempo del ciudadano.
          </p>
          <div className="civia-filter-bar" style={{ gridTemplateColumns: '1fr 1fr', marginBottom: '0.65rem' }}>
            <div className="civia-field">
              <label htmlFor="mgmt-assigned">Entidad o dependencia asignada</label>
              <input
                id="mgmt-assigned"
                type="text"
                placeholder="Ej. Secretaría de Infraestructura, Dagma, Uaesp"
                value={managementAssignedTo}
                onChange={(e) => setManagementAssignedTo(e.target.value)}
              />
            </div>
            <div className="civia-field">
              <label htmlFor="mgmt-status">Estado de revisión interna</label>
              <select
                id="mgmt-status"
                value={managementReviewStatus}
                onChange={(e) => setManagementReviewStatus(e.target.value)}
              >
                <option value="PENDING_REVIEW">Pendiente de revisión</option>
                <option value="IN_REVIEW">En evaluación técnica</option>
                <option value="REVIEWED">Revisado y priorizado</option>
              </select>
            </div>
          </div>
          <div className="civia-field" style={{ marginBottom: '0.75rem' }}>
            <label htmlFor="mgmt-note">Nota pública para el ciudadano (se registra en la trazabilidad)</label>
            <input
              id="mgmt-note"
              type="text"
              placeholder="Ej. Cuadrilla técnica programada para inspección en terreno este jueves..."
              value={managementPublicNote}
              onChange={(e) => setManagementPublicNote(e.target.value)}
            />
          </div>
          <button
            type="button"
            className="civia-btn accent sm"
            disabled={savingManagement}
            onClick={() => void handleSaveManagement(rep.id)}
          >
            {savingManagement ? 'Guardando gestión...' : 'Guardar Asignación y Publicar Nota'}
          </button>
        </div>
      )}
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
              Asistente Ciudadano
            </button>
            <button
              type="button"
              className={`civia-nav-btn ${activeTab === 'admin' ? 'active' : ''}`}
              onClick={() => setActiveTab('admin')}
            >
              Observabilidad Admin
              {adminNotifs && adminNotifs.unread_total > 0 && (
                <span className="civia-notif-count-badge">
                  {adminNotifs.unread_total}
                </span>
              )}
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

        {/* Estadísticas reales de reportes ciudadanos */}
        {stats && (
          <section className="civia-stats-grid" aria-label="Estadísticas de reportes ciudadanos">
            <div className="civia-stat-card">
              <div className="civia-stat-label">Total Reportes BD</div>
              <div className="civia-stat-value">{stats.total_reports}</div>
              <div className="civia-stat-sub">Reportes guardados</div>
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

        {/* PESTAÑA 1: EXPLORAR MAPA Y REPORTES */}
        {activeTab === 'explorar' && (
          <>
            {selectedReport && renderInspectionPanel(selectedReport, () => {
              setSelectedReport(null);
              setTimeout(() => {
                if (lastFocusedElementRef.current && typeof lastFocusedElementRef.current.focus === 'function') {
                  lastFocusedElementRef.current.focus();
                }
              }, 50);
            })}
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
                    <option value="PENDING_ANALYSIS">Pendiente de diagnóstico</option>
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
                        Ver detalle del reporte
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
              Flujo vertical completo: captura de evidencia y GPS → guardado seguro del reporte → diagnóstico asistido por IA → confirmación o corrección ciudadana.
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

                  {/* Evidencia fotográfica: Cámara, Subida o Muestras sintéticas */}
                  <div
                    style={{
                      background: '#f5f9f8',
                      padding: '1rem',
                      borderRadius: '10px',
                      border: '1px solid var(--civia-border)',
                    }}
                  >
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        flexWrap: 'wrap',
                        gap: '0.5rem',
                        marginBottom: '0.65rem',
                      }}
                    >
                      <label
                        htmlFor="rep-photo"
                        style={{ fontWeight: 700, fontSize: '0.92rem', color: 'var(--civia-teal-dark)' }}
                      >
                        Fotografía de evidencia * (JPEG, PNG o WEBP, máx. 5 MB)
                      </label>
                      {formPhoto && (
                        <button
                          type="button"
                          className="civia-btn secondary"
                          style={{ fontSize: '0.78rem', padding: '0.3rem 0.6rem' }}
                          onClick={handleDiscardPhoto}
                        >
                          ✕ Cambiar fotografía
                        </button>
                      )}
                    </div>

                    {cameraError && (
                      <div
                        className="civia-alert error"
                        style={{ marginBottom: '0.75rem', fontSize: '0.84rem' }}
                      >
                        {cameraError}
                      </div>
                    )}

                    {/* Visor de cámara en vivo */}
                    {isCameraActive && (
                      <div
                        style={{
                          background: '#0f172a',
                          padding: '0.75rem',
                          borderRadius: '10px',
                          textAlign: 'center',
                          marginBottom: '0.85rem',
                        }}
                      >
                        <video
                          ref={videoRef}
                          autoPlay
                          playsInline
                          muted
                          style={{
                            width: '100%',
                            maxHeight: '300px',
                            objectFit: 'cover',
                            borderRadius: '8px',
                            backgroundColor: '#000',
                          }}
                        />
                        <div
                          style={{
                            marginTop: '0.65rem',
                            display: 'flex',
                            gap: '0.6rem',
                            justifyContent: 'center',
                          }}
                        >
                          <button
                            type="button"
                            className="civia-btn accent"
                            onClick={captureCameraFrame}
                          >
                            📸 Capturar fotografía ahora
                          </button>
                          <button
                            type="button"
                            className="civia-btn secondary"
                            onClick={stopCamera}
                          >
                            Cancelar cámara
                          </button>
                        </div>
                      </div>
                    )}

                    {/* Vista previa si ya hay foto seleccionada/capturada */}
                    {formPhotoPreview && !isCameraActive && (
                      <div style={{ marginBottom: '0.85rem' }}>
                        <div
                          style={{
                            background: '#0f172a',
                            borderRadius: '8px',
                            overflow: 'hidden',
                            display: 'flex',
                            justifyContent: 'center',
                            alignItems: 'center',
                            minHeight: '160px',
                            maxHeight: '260px',
                          }}
                        >
                          <img
                            src={formPhotoPreview}
                            alt="Vista previa de evidencia"
                            style={{
                              maxWidth: '100%',
                              maxHeight: '260px',
                              objectFit: 'contain',
                              display: 'block',
                            }}
                          />
                        </div>
                        <div
                          style={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'center',
                            flexWrap: 'wrap',
                            gap: '0.5rem',
                            marginTop: '0.45rem',
                          }}
                        >
                          <div style={{ fontSize: '0.82rem', color: 'var(--civia-muted)' }}>
                            Archivo listo: <strong>{formPhoto?.name}</strong> (
                            {Math.round((formPhoto?.size || 0) / 1024)} KB)
                          </div>
                          {formIsSynthetic && (
                            <div
                              style={{
                                background: '#e8f4f8',
                                color: '#0f4c5c',
                                fontSize: '0.8rem',
                                fontWeight: 600,
                                padding: '0.25rem 0.55rem',
                                borderRadius: '6px',
                                border: '1px solid #b6d4db',
                              }}
                            >
                              ℹ Imagen generada con IA · Simulación
                            </div>
                          )}
                        </div>
                      </div>
                    )}

                    {/* Opciones de captura o subida cuando no hay foto activa */}
                    {!formPhoto && !isCameraActive && (
                      <>
                        <div
                          onDragOver={(e) => {
                            e.preventDefault();
                            setIsDragOver(true);
                          }}
                          onDragLeave={() => setIsDragOver(false)}
                          onDrop={handleDropPhoto}
                          style={{
                            border: `2px dashed ${isDragOver ? 'var(--civia-teal)' : '#b4c9c6'}`,
                            background: isDragOver ? '#eef7f6' : '#ffffff',
                            borderRadius: '8px',
                            padding: '1.1rem 0.9rem',
                            textAlign: 'center',
                            transition: 'all 0.2s ease',
                            marginBottom: '0.85rem',
                          }}
                        >
                          <p style={{ margin: '0 0 0.65rem 0', fontWeight: 600, fontSize: '0.9rem' }}>
                            Tome una foto en el lugar o seleccione una imagen de su dispositivo
                          </p>
                          <div
                            style={{
                              display: 'flex',
                              gap: '0.6rem',
                              justifyContent: 'center',
                              flexWrap: 'wrap',
                            }}
                          >
                            <button
                              type="button"
                              className="civia-btn accent"
                              onClick={() => void startCamera()}
                            >
                              📷 Tomar fotografía
                            </button>
                            <button
                              type="button"
                              className="civia-btn secondary"
                              onClick={() => fileInputRef.current?.click()}
                            >
                              📁 Subir fotografía
                            </button>
                          </div>
                          <p
                            style={{
                              margin: '0.55rem 0 0 0',
                              fontSize: '0.78rem',
                              color: 'var(--civia-muted)',
                            }}
                          >
                            O arrastre y suelte aquí su fotografía (JPEG, PNG o WEBP)
                          </p>
                          <input
                            ref={fileInputRef}
                            id="rep-photo"
                            type="file"
                            accept="image/jpeg,image/png,image/webp"
                            onChange={handlePhotoChange}
                            style={{ display: 'none' }}
                          />
                        </div>

                        {/* Muestras sintéticas discretas para prueba académica */}
                        <details className="civia-demo-details">
                          <summary>🔬 Opciones de prueba con muestras sintéticas (Solo evaluación académica)</summary>
                          <div style={{ marginTop: '0.6rem' }}>
                            <div
                              style={{
                                display: 'flex',
                                flexWrap: 'wrap',
                                gap: '0.4rem',
                              }}
                            >
                              {(
                                [
                                  ['HUECO', '🕳️ Hueco vial'],
                                  ['BASURAS', '🗑️ Basuras'],
                                  ['TALA', '🌳 Tala / Ramas'],
                                  ['QUEMA', '🔥 Quema'],
                                  ['OTRO', '⚡ Poste / Cables'],
                                ] as const
                              ).map(([cat, label]) => (
                                <button
                                  key={cat}
                                  type="button"
                                  className="civia-btn secondary sm"
                                  onClick={() => void handleSelectSyntheticSample(cat)}
                                >
                                  {label}
                                </button>
                              ))}
                            </div>
                          </div>
                        </details>
                      </>
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
            {newlyCreatedReport && (
              <div className="civia-success-banner" role="region" aria-label="Resultado de registro de reporte">
                <h3
                  ref={successHeadingRef}
                  tabIndex={-1}
                  style={{
                    margin: '0 0 0.5rem 0',
                    color: '#064e3b',
                    fontSize: '1.3rem',
                    outline: 'none',
                  }}
                >
                  🎉 ¡Tu reporte ha sido registrado exitosamente!
                </h3>
                <p style={{ margin: '0 0 0.85rem 0', color: '#065f46', fontSize: '0.92rem' }}>
                  Guarda tu número de radicado para hacer seguimiento o presentar solicitudes adicionales sobre este incidente.
                </p>

                <div className="civia-success-code-box">
                  <div>
                    <div style={{ fontSize: '0.78rem', textTransform: 'uppercase', color: '#047857', fontWeight: 700 }}>
                      Número de Radicado Oficial
                    </div>
                    <div className="civia-tracking-display">
                      {newlyCreatedReport.tracking_code}
                    </div>
                  </div>
                  <button
                    type="button"
                    className="civia-btn secondary sm"
                    onClick={() => void handleCopyTrackingCode(newlyCreatedReport.tracking_code)}
                    aria-label="Copiar número de radicado al portapapeles"
                  >
                    {copiedRadicado ? '✓ ¡Radicado copiado!' : '📋 Copiar radicado'}
                  </button>
                </div>

                {renderExternalDeliveryNotice()}

                <div style={{ display: 'flex', gap: '0.65rem', flexWrap: 'wrap', marginTop: '1rem' }}>
                  <button
                    type="button"
                    className="civia-btn secondary"
                    onClick={() => {
                      setNewlyCreatedReport(null);
                      setActiveTab('reportar');
                    }}
                  >
                    ➕ Registrar otro reporte
                  </button>
                  <button
                    type="button"
                    className="civia-btn secondary"
                    onClick={() => {
                      setNewlyCreatedReport(null);
                      setActiveTab('explorar');
                    }}
                  >
                    🗺️ Volver al mapa de reportes
                  </button>
                </div>
              </div>
            )}

            <h2>Seguimiento de Reporte mediante Código de Radicado</h2>
            <p style={{ color: 'var(--civia-muted)', marginTop: 0 }}>
              Consulte el estado de atención, el diagnóstico y el historial de trazabilidad de su reporte ingresando su número de radicado.
            </p>

            <form
              onSubmit={(e) => void handleSearchTrackingCode(e)}
              style={{ display: 'flex', gap: '0.65rem', flexWrap: 'wrap', marginBottom: '1.25rem' }}
            >
              <input
                type="text"
                aria-label="Código de radicado"
                value={trackingInput}
                onChange={(e) => setTrackingInput(e.target.value)}
                placeholder="Ej. CIV-2026-DEMO0001"
                style={{ padding: '0.65rem 0.85rem', borderRadius: '8px', border: '1px solid #bfd0cd', minWidth: '260px' }}
              />
              <button type="submit" className="civia-btn" disabled={trackingBusy}>
                {trackingBusy ? 'Consultando reporte...' : 'Consultar Radicado'}
              </button>
            </form>

            <details className="civia-demo-details" style={{ marginBottom: '1.25rem' }}>
              <summary>🔬 Radicados de prueba para evaluación (Demostración académica)</summary>
              <div style={{ display: 'flex', gap: '0.45rem', flexWrap: 'wrap', marginTop: '0.6rem' }}>
                {['CIV-2026-DEMO0001', 'CIV-2026-DEMO0002', 'CIV-2026-DEMO0004', 'CIV-2026-DEMO0008'].map(
                  (code) => (
                    <button
                      key={code}
                      type="button"
                      className="civia-btn secondary sm"
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
            </details>

            {trackedReport ? (
              renderInspectionPanel(trackedReport, () => {
                setTrackedReport(null);
                setNewlyCreatedReport(null);
                setTimeout(() => {
                  const inputEl = document.querySelector('input[aria-label="Código de radicado"]') as HTMLElement | null;
                  if (inputEl && typeof inputEl.focus === 'function') {
                    inputEl.focus();
                  } else if (lastFocusedElementRef.current && typeof lastFocusedElementRef.current.focus === 'function') {
                    lastFocusedElementRef.current.focus();
                  }
                }, 50);
              })
            ) : (
              <div
                style={{
                  background: '#f9fcfb',
                  border: '1px dashed #c0d5d0',
                  borderRadius: '8px',
                  padding: '2.5rem 1.5rem',
                  textAlign: 'center',
                  color: 'var(--civia-muted)',
                }}
              >
                <div style={{ fontSize: '2.2rem', marginBottom: '0.5rem' }}>🔍</div>
                <h3 style={{ margin: '0 0 0.35rem 0', color: 'var(--civia-teal-dark)' }}>
                  Consulta el estado y avance de tu reporte
                </h3>
                <p style={{ margin: 0, fontSize: '0.9rem', maxWidth: '520px', marginLeft: 'auto', marginRight: 'auto' }}>
                  Ingresa tu número de radicado en el campo superior para revisar los datos registrados, la clasificación confirmada y los hitos de gestión.
                </p>
              </div>
            )}
          </section>
        )}

        {/* PESTAÑA 4: ASISTENTE AGÉNTICO CON HERRAMIENTAS Y 4 LÍMITES */}
        {activeTab === 'asistente' && (
          <section className="civia-panel">
            <h2>Asistente Ciudadano de Consulta y Gestión</h2>
            <p style={{ color: 'var(--civia-muted)', marginTop: 0 }}>
              El asistente ciudadano te ayuda a consultar información sobre reportes en Santiago de Cali, conocer el estado de incidentes y registrar observaciones de forma guiada y segura. Cualquier actualización crítica es supervisada por operadores calificados.
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

            {(() => {
              const effectiveOpId = agentResponse?.operation_id || activeAttempt?.operationId;
              const effectiveOpToken = agentResponse?.query_token || activeAttempt?.operationToken;
              const effectiveOpStatus = agentResponse?.operation_status || activeAttempt?.operationStatus;

              if (!agentResponse && !effectiveOpId) {
                return null;
              }

              return (
                <div style={{ background: '#f5f9f8', padding: '1.1rem', borderRadius: '10px', border: '1px solid var(--civia-border)' }}>
                  {agentResponse && (
                    <>
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

                      {agentResponse.tools_invoked && agentResponse.tools_invoked.length > 0 && (
                        <div>
                          <strong style={{ fontSize: '0.88rem' }}>
                            Acciones de consulta realizadas ({agentResponse.tools_invoked.length}):
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
                      )}
                    </>
                  )}

                  {effectiveOpId && (
                    <div style={{ marginTop: '0.8rem', padding: '0.8rem', background: '#eef6f5', borderRadius: '8px', border: '1px solid #c8deda' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
                        <span style={{ fontSize: '0.85rem' }}>
                          <strong>ID Operación:</strong> <code>{effectiveOpId}</code>
                          {effectiveOpStatus && (
                            <span className="civia-badge status" style={{ marginLeft: '0.5rem' }}>
                              {effectiveOpStatus}
                            </span>
                          )}
                        </span>
                        <button
                          type="button"
                          className="civia-btn secondary"
                          style={{ padding: '0.3rem 0.7rem', fontSize: '0.8rem' }}
                          disabled={checkingOperation}
                          onClick={() => handleCheckOperationStatus(effectiveOpId, effectiveOpToken ?? undefined)}
                        >
                          {checkingOperation ? 'Consultando...' : 'Verificar estado definitivo'}
                        </button>
                      </div>

                      {operationStatus && (
                        <div style={{ marginTop: '0.6rem', padding: '0.6rem', background: '#ffffff', borderRadius: '6px', fontSize: '0.82rem' }}>
                          <div><strong>Estado persistido:</strong> {operationStatus.status}</div>
                          {operationStatus.target_id && <div><strong>Reporte objetivo:</strong> {operationStatus.target_id}</div>}
                          {operationStatus.operation_type && <div><strong>Tipo de operación:</strong> {operationStatus.operation_type}</div>}
                          {operationStatus.result_payload && (
                            <pre style={{ margin: '0.4rem 0 0', padding: '0.4rem', background: '#f5f5f5', borderRadius: '4px', maxHeight: '120px', overflow: 'auto' }}>
                              {JSON.stringify(operationStatus.result_payload, null, 2)}
                            </pre>
                          )}
                          {operationStatus.error_message && (
                            <div style={{ color: '#d32f2f', marginTop: '0.3rem' }}>
                              <strong>Fallo:</strong> {operationStatus.error_message}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )}

                  <div style={{ marginTop: '0.85rem', display: 'flex', justifyContent: 'flex-end' }}>
                    <button
                      type="button"
                      className="civia-btn secondary"
                      style={{ fontSize: '0.78rem', padding: '0.3rem 0.65rem' }}
                      onClick={handleClearAgentSession}
                    >
                      Nueva consulta / Limpiar sesión
                    </button>
                  </div>
                </div>
              );
            })()}
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
                placeholder="Ingrese ADMIN_TOKEN de .env"
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
                {/* BANDEJA DE REPORTES RECIBIDOS (NOTIFICACIONES INTERNAS) */}
                <div style={{ background: '#f5f9f8', padding: '1.1rem', borderRadius: '10px', border: '1px solid var(--civia-border)', marginBottom: '1.25rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.65rem', marginBottom: '0.75rem' }}>
                    <div>
                      <h3 style={{ margin: 0, fontSize: '1.05rem', color: 'var(--civia-teal-dark)' }}>
                        📬 Bandeja de Reportes Recibidos (Notificaciones Internas)
                      </h3>
                      <p style={{ margin: '0.2rem 0 0', fontSize: '0.82rem', color: 'var(--civia-muted)' }}>
                        Alertas generadas automáticamente al registrarse reportes en CIVIA. No modifica el estado de los reportes.
                      </p>
                    </div>
                    {adminNotifs && adminNotifs.unread_total > 0 && (
                      <button
                        type="button"
                        className="civia-btn secondary sm"
                        onClick={() => void handleMarkAllNotifsRead()}
                      >
                        ✓ Marcar todas como leídas
                      </button>
                    )}
                  </div>

                  {/* Filtros y contadores */}
                  <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center', marginBottom: '0.85rem' }}>
                    <span style={{ fontSize: '0.82rem', fontWeight: 600 }}>Filtrar:</span>
                    {[
                      { key: 'ALL', label: `Todos (${adminNotifs?.total || 0})` },
                      { key: 'CITIZEN', label: `Ciudadanos (${adminNotifs ? (adminNotifs.total - (adminNotifs.unread_synthetic || 0)) : 0})` },
                      { key: 'SYNTHETIC', label: 'Sintéticos Demo' },
                    ].map((f) => (
                      <button
                        key={f.key}
                        type="button"
                        className={`civia-btn sm ${notifFilter === f.key ? 'accent' : 'secondary'}`}
                        onClick={() => setNotifFilter(f.key)}
                      >
                        {f.label}
                      </button>
                    ))}
                    <label style={{ display: 'inline-flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.82rem', marginLeft: '0.5rem', cursor: 'pointer' }}>
                      <input
                        type="checkbox"
                        checked={notifUnreadOnly}
                        onChange={(e) => setNotifUnreadOnly(e.target.checked)}
                      />
                      Solo no leídas ({adminNotifs?.unread_total || 0})
                    </label>
                  </div>

                  {/* Lista de notificaciones */}
                  {adminNotifs && adminNotifs.items.length > 0 ? (
                    <div className="civia-notif-grid">
                      {adminNotifs.items.map((nt: AdminNotificationItem) => (
                        <div
                          key={nt.id}
                          className={`civia-notif-item ${!nt.is_read ? 'unread' : ''}`}
                        >
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flex: 1, minWidth: '240px' }}>
                            {nt.photo_url && (
                              <img
                                src={nt.photo_url}
                                alt="Evidencia"
                                style={{ width: '48px', height: '48px', borderRadius: '6px', objectFit: 'cover', background: '#e2e8f0' }}
                              />
                            )}
                            <div>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', flexWrap: 'wrap' }}>
                                <strong style={{ fontSize: '0.88rem' }}>{nt.tracking_code}</strong>
                                {nt.category && <span className={`civia-badge cat-${nt.category}`}>{nt.category}</span>}
                                {nt.is_synthetic && <span className="civia-badge synthetic">Sintético</span>}
                                {!nt.is_read && (
                                  <span style={{ fontSize: '0.72rem', background: 'var(--civia-amber)', color: '#fff', padding: '0.1rem 0.4rem', borderRadius: '4px', fontWeight: 700 }}>
                                    NUEVO
                                  </span>
                                )}
                              </div>
                              <p style={{ margin: '0.2rem 0 0', fontSize: '0.82rem', color: '#334155' }}>
                                {nt.message}
                              </p>
                              <div style={{ fontSize: '0.75rem', color: 'var(--civia-muted)', marginTop: '0.2rem' }}>
                                Recibido: {new Date(nt.created_at).toLocaleString('es-CO')}
                              </div>
                            </div>
                          </div>

                          <div style={{ display: 'flex', gap: '0.4rem', alignItems: 'center' }}>
                            {!nt.is_read && (
                              <button
                                type="button"
                                className="civia-btn secondary sm"
                                onClick={() => void handleMarkNotifRead(nt.id)}
                              >
                                Marcar leída
                              </button>
                            )}
                            <button
                              type="button"
                              className="civia-btn sm"
                              onClick={async () => {
                                const rep = await fetchReportByCode(nt.tracking_code);
                                openReportInspection(rep);
                                setActiveTab('explorar');
                              }}
                            >
                              Ver reporte y gestionar
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div style={{ fontSize: '0.85rem', color: 'var(--civia-muted)', textAlign: 'center', padding: '1rem' }}>
                      No hay notificaciones con el filtro seleccionado.
                    </div>
                  )}
                </div>

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
