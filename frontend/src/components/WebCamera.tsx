import { useEffect, useRef, useState } from 'react';

export function WebCamera({ onCapture, onError }: { onCapture: (file: File) => void; onError: (message: string) => void }) {
  const video = useRef<HTMLVideoElement | null>(null);
  const session = useRef<{ stream?: MediaStream } | null>(null);
  const [open, setOpen] = useState(false);
  const [ready, setReady] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => () => {
    session.current?.stream?.getTracks().forEach((track) => track.stop());
    session.current = null;
  }, []);

  function close() {
    session.current?.stream?.getTracks().forEach((track) => track.stop());
    session.current = null;
    if (video.current) video.current.srcObject = null;
    setOpen(false);
    setReady(false);
    setSaving(false);
  }

  async function start() {
    if (session.current) return;
    if (!navigator.mediaDevices?.getUserMedia) {
      onError('La cámara requiere HTTPS o localhost en un navegador compatible. También puedes seleccionar una foto.');
      return;
    }
    const request: { stream?: MediaStream } = {};
    session.current = request;
    onError('');
    setOpen(true);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' } }, audio: false });
      const preview = video.current;
      if (session.current !== request || !preview) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      request.stream = stream;
      preview.srcObject = stream;
      await preview.play();
    } catch (error) {
      if (session.current !== request) return;
      close();
      onError(error instanceof DOMException && error.name === 'NotAllowedError'
        ? 'Permite el acceso a la cámara en el navegador o selecciona una foto.'
        : 'No se pudo abrir la cámara. Puedes seleccionar una foto.');
    }
  }

  function capture() {
    const preview = video.current;
    const request = session.current;
    if (!request || !preview?.videoWidth || !preview.videoHeight || saving) return;
    const canvas = document.createElement('canvas');
    const scale = Math.min(1, 1920 / Math.max(preview.videoWidth, preview.videoHeight));
    canvas.width = Math.max(1, Math.round(preview.videoWidth * scale));
    canvas.height = Math.max(1, Math.round(preview.videoHeight * scale));
    const context = canvas.getContext('2d');
    if (!context) {
      onError('No se pudo capturar la foto. Puedes seleccionar una foto.');
      close();
      return;
    }
    context.drawImage(preview, 0, 0, canvas.width, canvas.height);
    setSaving(true);
    canvas.toBlob((blob) => {
      if (session.current !== request) return;
      close();
      if (blob) onCapture(new File([blob], 'foto-civia.jpg', { type: 'image/jpeg' }));
      else onError('No se pudo guardar la foto. Vuelve a intentarlo o selecciona una foto.');
    }, 'image/jpeg', 0.9);
  }

  return <>
    <video className="web-camera-preview" ref={video} hidden={!open} autoPlay muted playsInline
      aria-label="Vista previa de la cámara" onCanPlay={() => setReady(Boolean(session.current?.stream))} />
    {open ? <div className="actions">
      {!ready && <p role="status">Abriendo cámara…</p>}
      <button type="button" disabled={!ready || saving} onClick={capture}>Tomar foto</button>
      <button type="button" className="secondary" onClick={close}>Cerrar cámara</button>
    </div> : <button type="button" className="secondary" onClick={() => void start()}>Abrir cámara</button>}
  </>;
}
