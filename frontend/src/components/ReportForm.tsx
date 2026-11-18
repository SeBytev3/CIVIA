import { useCallback, useEffect, useRef, useState } from 'react';
import { CameraSource } from '@capacitor/camera';
import { CiviaError, submitReport } from '../api';
import { cancelNativeRecording, findLocation, isNative, randomId, startNativeRecording, stopNativeRecording, takeNativePhoto } from '../device';
import { blankDraft, draftStorage, type Draft } from '../draft';
import type { ReportItem } from '../types';
import { CaliMap } from './CaliMap';
import { AnalysisState } from './ReportDetail';

const AUDIO_LIMIT_MS = 60_000;
const AUDIO_LIMIT_BYTES = 5 * 1024 * 1024;
const IMAGE_LIMIT_BYTES = 5 * 1024 * 1024;
const SENT_PENDING = 'Tu reporte está guardado en este dispositivo y pendiente de envío. Podrás enviarlo cuando recuperes la conexión.';

function validateAudio(file: File): Promise<File> {
  if (file.size > AUDIO_LIMIT_BYTES) return Promise.reject(new Error('La nota de voz debe pesar como máximo 5 MB.'));
  return new Promise((resolve, reject) => {
    const objectUrl = URL.createObjectURL(file);
    const audio = new Audio(objectUrl);
    const timer = window.setTimeout(() => finish(new Error('No se pudo verificar la duración de la nota de voz.')), 7000);
    const finish = (error?: Error) => {
      window.clearTimeout(timer);
      URL.revokeObjectURL(objectUrl);
      audio.removeAttribute('src');
      if (error) reject(error);
      else resolve(file);
    };
    audio.onloadedmetadata = () => finish(Number.isFinite(audio.duration) && audio.duration <= AUDIO_LIMIT_MS / 1000
      ? undefined : new Error('La nota de voz debe durar como máximo 60 segundos.'));
    audio.onerror = () => finish(new Error('El formato de la nota de voz no es compatible.'));
  });
}

function useAudioCapture(onCapture: (file: File) => void, onError: (message: string) => void) {
  const [recording, setRecording] = useState(false);
  const active = useRef<{ recorder: MediaRecorder; timer: number } | null>(null);
  const nativeTimer = useRef<number | null>(null);
  const acquiring = useRef(false);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      if (nativeTimer.current !== null) {
        window.clearTimeout(nativeTimer.current);
        nativeTimer.current = null;
        void cancelNativeRecording().catch(() => {});
      }
      const capture = active.current;
      if (capture) {
        capture.recorder.onstop = null;
        window.clearTimeout(capture.timer);
        if (capture.recorder.state === 'recording') capture.recorder.stop();
        capture.recorder.stream.getTracks().forEach((track) => track.stop());
        active.current = null;
      }
    };
  }, []);

  function stop() {
    if (nativeTimer.current !== null) {
      window.clearTimeout(nativeTimer.current);
      nativeTimer.current = null;
      void stopNativeRecording().then((file) => {
        if (mounted.current) onCapture(file);
      }).catch(() => {
        if (mounted.current) onError('No se pudo guardar la nota de voz.');
      }).finally(() => { if (mounted.current) setRecording(false); });
      return;
    }
    const capture = active.current;
    if (capture?.recorder.state === 'recording') capture.recorder.stop();
  }

  async function start() {
    if (acquiring.current || active.current || nativeTimer.current !== null) return;
    acquiring.current = true;
    let stream: MediaStream | undefined;
    try {
      if (isNative) {
        await startNativeRecording();
        if (!mounted.current) { await cancelNativeRecording(); return; }
        nativeTimer.current = window.setTimeout(stop, AUDIO_LIMIT_MS - 500);
        setRecording(true);
        return;
      }
      const format = [
        { mimeType: 'audio/webm;codecs=opus', suffix: 'webm' },
        { mimeType: 'audio/ogg;codecs=opus', suffix: 'ogg' },
      ].find(({ mimeType }) => window.MediaRecorder?.isTypeSupported(mimeType));
      if (!format) throw new Error();
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (!mounted.current) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      const recorder = new MediaRecorder(stream, { mimeType: format.mimeType, audioBitsPerSecond: 64000 });
      const chunks: Blob[] = [];
      let bytes = 0;
      recorder.ondataavailable = ({ data }) => {
        chunks.push(data);
        bytes += data.size;
        if (bytes > AUDIO_LIMIT_BYTES) stop();
      };
      recorder.onstop = () => {
        window.clearTimeout(active.current?.timer);
        recorder.stream.getTracks().forEach((track) => track.stop());
        active.current = null;
        setRecording(false);
        if (bytes > AUDIO_LIMIT_BYTES) onError('La nota de voz supera 5 MB.');
        else if (bytes) onCapture(new File(chunks, `nota-de-voz.${format.suffix}`, { type: `audio/${format.suffix}` }));
      };
      recorder.start(500);
      active.current = { recorder, timer: window.setTimeout(stop, AUDIO_LIMIT_MS - 500) };
      setRecording(true);
    } catch (reason) {
      stream?.getTracks().forEach((track) => track.stop());
      if (mounted.current) onError((reason as { code?: string } | null)?.code === 'permission'
        ? 'Permite el acceso al micrófono para grabar. También puedes adjuntar un archivo de audio.'
        : 'No se pudo grabar. Puedes adjuntar un archivo de audio compatible.');
    } finally {
      acquiring.current = false;
    }
  }

  return { recording, start, stop };
}

function BlobPreview({ file, kind }: { file?: File; kind: 'photo' | 'audio' }) {
  const [url, setUrl] = useState('');
  useEffect(() => {
    if (!file) {
      setUrl('');
      return;
    }
    const next = URL.createObjectURL(file);
    setUrl(next);
    return () => URL.revokeObjectURL(next);
  }, [file]);
  if (!url || !file) return null;
  return kind === 'photo' ? <img className="evidence" src={url} alt="Evidencia seleccionada" /> : <audio controls src={url} />;
}

export function ReportForm({ ownerId, onNavigate }: { ownerId: string; onNavigate?: () => void }) {
  const [draft, setDraft] = useState<Draft | null>(null);
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [legacyAvailable, setLegacyAvailable] = useState(false);
  const [receipt, setReceipt] = useState<ReportItem | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [mapOpen, setMapOpen] = useState(false);
  const [finding, setFinding] = useState(false);
  const latest = useRef<Draft | null>(null);
  const storage = useRef<Awaited<ReturnType<typeof draftStorage>> | null>(null);
  const sending = useRef(false);
  const writes = useRef<Promise<unknown>>(Promise.resolve());

  useEffect(() => {
    let cancelled = false;
    async function load() {
      const target = await draftStorage(ownerId);
      const [saved, old] = await Promise.all([target.read(), target.readLegacy()]);
      if (cancelled) return;
      const restored = saved ?? blankDraft();
      storage.current = target;
      latest.current = restored;
      setLegacyAvailable(Boolean(old) && !saved);
      setDraft(restored);
    }
    load().catch((reason: unknown) => {
      if (!cancelled) setError(reason instanceof CiviaError ? reason.message
        : 'No se pudo abrir el almacenamiento de borradores de este dispositivo.');
    });
    return () => { cancelled = true; };
  }, [ownerId, loadAttempt]);

  async function recoverLegacy() {
    const target = storage.current;
    if (!target) return;
    setError('');
    setBusy(true);
    try {
      await writes.current;
      const restored = await target.recoverLegacy();
      if (restored) {
        latest.current = restored;
        setDraft(restored);
        setLegacyAvailable(false);
      } else {
        setError('No se pudo recuperar el borrador anterior. Actualiza la página y verifica tus borradores.');
      }
    } catch {
      setError('No se pudo recuperar el borrador anterior. Intenta nuevamente.');
    } finally {
      setBusy(false);
    }
  }

  const persist = useCallback((value: Draft) => {
    const target = storage.current;
    if (!target) return Promise.reject(new Error('No se pudo abrir el almacenamiento de borradores.'));
    latest.current = value;
    setDraft(value);
    const write = writes.current.catch(() => {}).then(() => target.save(value));
    writes.current = write;
    return write;
  }, []);

  const update = useCallback((changes: Partial<Draft>) => {
    if (!latest.current || latest.current.pending) return;
    setLegacyAvailable(false);
    void persist({ ...latest.current, ...changes }).catch(() => {
      setError('No se pudo guardar el borrador. Libera espacio e intenta nuevamente.');
    });
  }, [persist]);

  const recording = useAudioCapture((audio) => update({ audio }), setError);

  function selectPhoto(photo?: File) {
    if (!photo) return;
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(photo.type) || photo.size > IMAGE_LIMIT_BYTES) {
      setError('Selecciona una foto JPEG, PNG o WebP de hasta 5 MB.');
      return;
    }
    setError('');
    update({ photo });
  }

  const send = useCallback(async () => {
    const value = latest.current;
    const target = storage.current;
    if (!value?.photo || value.latitude === undefined || value.longitude === undefined ||
        value.description.trim().length < 10 || value.title.trim().length < 4 || sending.current || !target) return;
    sending.current = true;
    setBusy(true);
    setError('');
    try {
      await persist({ ...value, pending: true });
    } catch {
      latest.current = value;
      setDraft(value);
      setBusy(false);
      sending.current = false;
      setError('No se pudo guardar el borrador. Libera espacio e intenta nuevamente.');
      return;
    }
    try {
      const data = new FormData();
      data.set('title', value.title);
      data.set('description', value.description);
      data.set('latitude', String(value.latitude));
      data.set('longitude', String(value.longitude));
      data.set('photo', value.photo);
      if (value.audio) data.set('audio', value.audio);
      const created = await submitReport(data, value.key, ownerId, target.installationId);
      if (!created.id || !created.tracking_code) throw new CiviaError(0, 'CIVIA no confirmó la recepción.');
      setReceipt(created);
      latest.current = null;
      setDraft(null);
      try { await target.remove(); }
      catch { setError('El reporte se recibió. No se pudo limpiar el borrador del dispositivo.'); }
    } catch (reason) {
      if (reason instanceof CiviaError && [400, 413, 415, 422].includes(reason.status)) {
        try {
          await persist({ ...value, key: randomId(), pending: false });
          setError(reason.message);
        } catch {
          setError('No se pudo actualizar el borrador en el dispositivo.');
        }
      } else if (reason instanceof CiviaError && reason.status > 0 && reason.status < 500) {
        setError(reason.message);
      }
    } finally {
      setBusy(false);
      sending.current = false;
    }
  }, [ownerId, persist]);

  useEffect(() => {
    const retry = () => {
      if (latest.current?.pending) void send();
      else if (!storage.current) {
        setError('');
        setLoadAttempt((attempt) => attempt + 1);
      }
    };
    window.addEventListener('online', retry);
    window.addEventListener('civia-online', retry);
    return () => {
      window.removeEventListener('online', retry);
      window.removeEventListener('civia-online', retry);
    };
  }, [send]);

  const Heading = onNavigate ? 'h1' : 'h2';
  const SectionHeading = onNavigate ? 'h2' : 'h3';
  if (receipt) {
    return <section className="surface stack">
      <Heading>Reporte recibido</Heading>
      <p role="status">Tu reporte fue recibido correctamente.</p>
      <p>Radicado</p>
      <strong className="tracking-code">{receipt.tracking_code}</strong>
      <AnalysisState report={receipt} detailed />
      {receipt.analysis_status === 'PENDING' && <p>Si el análisis se demora, tu reporte seguirá guardado y será procesado automáticamente. No necesitas enviarlo nuevamente.</p>}
      {error && <p role="alert">{error}</p>}
      <div className="actions">
        <button disabled={busy} onClick={() => {
          try {
            const next = blankDraft();
            latest.current = next;
            setDraft(next);
            setReceipt(null);
            setMapOpen(false);
            setError('');
          } catch {
            setError('No se pudo abrir un reporte nuevo. Vuelve a cargar CIVIA.');
          }
        }}>Registrar otro reporte</button>
        {onNavigate && <button className="secondary" onClick={onNavigate}>Ver mis reportes</button>}
      </div>
    </section>;
  }
  if (!draft) return error ? <section className="surface stack">
    <p role="alert">{error}</p>
    <button onClick={() => { setError(''); setLoadAttempt((attempt) => attempt + 1); }}>Reintentar</button>
  </section> : <p role="status">Abriendo borrador…</p>;

  return <section className="surface report-form">
    <Heading>Nuevo reporte</Heading>
    {legacyAvailable &&
      <aside className="draft-recovery stack">
        <p>Hay un borrador anterior de tu cuenta. Si corresponde a esta instalación de CIVIA, puedes recuperarlo y revisarlo antes de enviarlo.</p>
        <button type="button" className="secondary" disabled={busy} onClick={() => void recoverLegacy()}>Recuperar borrador anterior</button>
      </aside>}
    <form className="stack" onSubmit={(event) => { event.preventDefault(); if (!recording.recording) void send(); }}>
      <fieldset disabled={busy || draft.pending} className="stack">
        <label>Título<input required minLength={4} maxLength={160} value={draft.title} onChange={(event) => update({ title: event.target.value })} /></label>
        <label>Descripción<textarea required minLength={10} maxLength={2000} rows={4} value={draft.description} onChange={(event) => update({ description: event.target.value })} /></label>
        <section className="stack">
          <SectionHeading>Ubicación</SectionHeading>
          {draft.latitude !== undefined && draft.longitude !== undefined && <p className="tracking-code">{draft.latitude.toFixed(6)}, {draft.longitude.toFixed(6)}</p>}
          <div className="actions">
            <button type="button" className="secondary" disabled={finding} onClick={async () => {
              setFinding(true);
              setError('');
              try { update(await findLocation()); }
              catch { setError('No se pudo obtener tu ubicación. Puedes elegirla en el mapa.'); }
              finally { setFinding(false); }
            }}>{finding ? 'Buscando ubicación…' : 'Usar mi ubicación'}</button>
            <button type="button" className="secondary" aria-expanded={mapOpen} onClick={() => setMapOpen(!mapOpen)}>Elegir en el mapa</button>
          </div>
          {mapOpen && <CaliMap reports={[]} selectable selectedLat={draft.latitude} selectedLon={draft.longitude} onPickCoords={(latitude, longitude) => update({ latitude, longitude })} height="260px" />}
        </section>
        <section className="stack">
          <SectionHeading>Fotografía</SectionHeading>
          {isNative ? <div className="actions">{[
            [CameraSource.Camera, 'Abrir cámara'],
            [CameraSource.Photos, 'Abrir galería'],
          ].map(([source, label]) => <button className="secondary" key={source} type="button" onClick={async () => {
            try { selectPhoto(await takeNativePhoto(source as CameraSource)); }
            catch { setError('No se agregó una foto. Revisa los permisos o vuelve a intentarlo.'); }
          }}>{label}</button>)}</div> : <>
            <label>Abrir cámara<input type="file" accept="image/*" capture="environment" onChange={(event) => selectPhoto(event.target.files?.[0])} /></label>
            <label>Seleccionar foto<input type="file" accept="image/jpeg,image/png,image/webp" onChange={(event) => selectPhoto(event.target.files?.[0])} /></label>
          </>}
          <BlobPreview file={draft.photo} kind="photo" />
        </section>
        <section className="stack">
          <SectionHeading>Nota de voz opcional</SectionHeading>
          <p>Hasta 60 segundos y 5 MB.</p>
          <div className="actions">
            {recording.recording
              ? <button type="button" onClick={recording.stop}>Detener grabación</button>
              : <button type="button" className="secondary" onClick={() => void recording.start()}>Grabar audio</button>}
            {draft.audio && <button type="button" className="secondary" onClick={() => update({ audio: undefined })}>Quitar audio</button>}
          </div>
          <label>Adjuntar audio<input type="file" accept="audio/wav,audio/mpeg,audio/ogg,audio/webm" onChange={async (event) => {
            const file = event.target.files?.[0];
            if (file) {
              try { update({ audio: await validateAudio(file) }); }
              catch (reason) { setError((reason as Error).message); }
            }
          }} /></label>
          <BlobPreview file={draft.audio} kind="audio" />
        </section>
      </fieldset>
      {error && <p role="alert">{error}</p>}
      {draft.pending && !busy && <p role="status">{SENT_PENDING}</p>}
      <button disabled={busy || recording.recording || !draft.photo || draft.latitude === undefined || draft.longitude === undefined} type="submit">
        {busy ? 'Guardando y enviando…' : draft.pending ? 'Reintentar envío' : 'Enviar reporte'}
      </button>
    </form>
  </section>;
}
