import { Capacitor, registerPlugin } from '@capacitor/core';
import { Camera, CameraResultType, CameraSource } from '@capacitor/camera';
import { Geolocation } from '@capacitor/geolocation';
import { fromBase64 } from './nativeConnection';

export const isNative = Capacitor.isNativePlatform();

export { randomId } from './nativeConnection';

const microphone = registerPlugin<{
  start(): Promise<void>;
  stop(): Promise<{ base64: string }>;
  cancel(): Promise<void>;
}>('CiviaAudio');

export const startNativeRecording = () => microphone.start();
export const cancelNativeRecording = () => microphone.cancel();
export async function stopNativeRecording() {
  const { base64 } = await microphone.stop();
  return new File([fromBase64(base64)], 'nota-de-voz.wav', { type: 'audio/wav' });
}

export async function takeNativePhoto(source: CameraSource): Promise<File> {
  const photo = await Camera.getPhoto({
    source,
    resultType: CameraResultType.Uri,
    quality: 84,
    width: 1920,
    height: 1920,
    saveToGallery: false,
  });
  if (!photo.webPath) throw new Error('No se pudo acceder a la fotografía.');
  const response = await fetch(photo.webPath);
  if (!response.ok) throw new Error('No se pudo acceder a la fotografía.');
  const blob = await response.blob();
  return new File([blob], `foto.${photo.format || 'jpeg'}`, { type: blob.type || 'image/jpeg' });
}

export async function findLocation() {
  const options = { enableHighAccuracy: true, timeout: 12000, maximumAge: 0 };
  const position = isNative
    ? await Geolocation.getCurrentPosition(options)
    : await new Promise<GeolocationPosition>((resolve, reject) => {
      if (!navigator.geolocation) reject(new Error('Ubicación no disponible'));
      else navigator.geolocation.getCurrentPosition(resolve, reject, options);
    });
  return { latitude: position.coords.latitude, longitude: position.coords.longitude };
}
