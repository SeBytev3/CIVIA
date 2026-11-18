import { registerPlugin, type PluginListenerHandle } from '@capacitor/core';

export interface NativeProfile {
  profileId: string;
  installationId: string;
  origin: string;
}

export interface Candidate {
  name: string;
  installationId: string;
  origins: string[];
}

interface Discovery {
  state: 'searching' | 'unavailable';
  candidates: Candidate[];
}

interface NativeReply {
  status: number;
  contentType?: string;
  json?: string;
  base64?: string;
}

interface MediaPart { type: string; base64: string }
interface Multipart {
  title: string;
  description: string;
  latitude: string;
  longitude: string;
  photo: MediaPart;
  audio?: MediaPart;
}

export const connection = registerPlugin<{
  getTrusted(): Promise<Partial<NativeProfile>>;
  startDiscovery(): Promise<void>;
  stopDiscovery(): Promise<void>;
  addListener(event: 'discoveryChanged', listener: (update: Discovery) => void): Promise<PluginListenerHandle>;
  addListener(event: 'networkChanged', listener: () => void): Promise<PluginListenerHandle>;
  pair(input: { requestId: string; code: string; origin?: string }): Promise<NativeProfile>;
  reconnect(input: { requestId: string; profileId: string; origin?: string }): Promise<NativeProfile>;
  decodeQr(input: { requestId: string; image: string }): Promise<{ code: string }>;
  cachedSession(input: { profileId: string }): Promise<{ json?: string }>;
  request(input: {
    requestId: string;
    profileId: string;
    ownerId?: string;
    method: string;
    path: string;
    idempotencyKey?: string;
    json?: string;
    multipart?: Multipart;
  }): Promise<NativeReply>;
  cancel(input: { requestId: string }): Promise<void>;
}>('CiviaConnection');

let profile: NativeProfile | undefined;
export function nativeProfile() { return profile; }
export function setNativeProfile(value: NativeProfile) { profile = value; }

export function randomId(): string {
  if (typeof crypto.randomUUID === 'function') return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (value) => value.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export function blobBase64(blob: Blob): Promise<string> {
  if (blob.size > 5 * 1024 * 1024) return Promise.reject(new Error('La evidencia supera el tamaño permitido.'));
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(',', 2)[1]);
    reader.onerror = () => reject(new Error('No se pudo leer el archivo.'));
    reader.readAsDataURL(blob);
  });
}

async function multipart(data: FormData): Promise<Multipart> {
  const photo = data.get('photo');
  const audio = data.get('audio');
  if (!(photo instanceof Blob)) throw new Error('Falta la fotografía del reporte.');
  return {
    title: String(data.get('title') ?? ''),
    description: String(data.get('description') ?? ''),
    latitude: String(data.get('latitude') ?? ''),
    longitude: String(data.get('longitude') ?? ''),
    photo: { type: photo.type, base64: await blobBase64(photo) },
    ...(audio instanceof Blob && { audio: { type: audio.type, base64: await blobBase64(audio) } }),
  };
}

export function fromBase64(encoded: string) {
  const decoded = atob(encoded);
  return Uint8Array.from(decoded, (value) => value.charCodeAt(0));
}

export async function nativeRequest(path: string, options: RequestInit, ownerId?: string, installationId?: string): Promise<Response> {
  const selected = profile;
  if (!selected || (installationId && installationId !== selected.installationId)) throw new Error('Conexión no disponible.');
  const signal = options.signal;
  const requestId = randomId();
  const headers = new Headers(options.headers);
  const parts = options.body instanceof FormData ? await multipart(options.body) : undefined;
  if (signal?.aborted || selected.profileId !== profile?.profileId) throw new Error('Solicitud cancelada.');
  const abort = () => { void connection.cancel({ requestId }).catch(() => {}); };
  signal?.addEventListener('abort', abort, { once: true });
  try {
    const result = await connection.request({
      requestId, profileId: selected.profileId, path, ownerId, method: options.method ?? 'GET',
      idempotencyKey: headers.get('Idempotency-Key') ?? undefined,
      json: typeof options.body === 'string' ? options.body : undefined,
      multipart: parts,
    });
    if (signal?.aborted || selected.profileId !== profile?.profileId) throw new Error('Solicitud cancelada.');
    const body = result.base64 ? fromBase64(result.base64) : result.json ?? null;
    return new Response(body, { status: result.status, headers: result.contentType ? { 'Content-Type': result.contentType } : undefined });
  } finally {
    signal?.removeEventListener('abort', abort);
  }
}
