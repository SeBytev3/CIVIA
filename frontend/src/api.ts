import { isNative, randomId } from './device';
import { connection, nativeProfile, nativeRequest } from './nativeConnection';
import type {
  AdminNotificationsResponse, AgentQueryResponse, AnalysisQueue, AuditEntry,
  DeadLetterJob, ObservabilityData, Page, PendingApprovalItem, PublicMapItem,
  ReportCategory, ReportEventItem, ReportItem, ReportSeverity, ReportStats, PublicStats, Role,
  Session, User,
} from './types';

let csrf = '';

const failureMessages: Record<number, string> = {
  400: 'Revisa los datos ingresados e intenta nuevamente.',
  401: 'La sesión no está disponible o las credenciales son incorrectas.',
  403: 'Tu cuenta no tiene autorización para realizar esta operación.',
  404: 'No se encontró el registro solicitado.',
  409: 'La operación entra en conflicto con el estado actual. Actualiza la información.',
  413: 'El tamaño de la evidencia supera el límite permitido.',
  415: 'El formato de la evidencia no es compatible.',
  422: 'Revisa los datos y el formato de la evidencia.',
  429: 'Hay demasiadas solicitudes. Intenta nuevamente en unos momentos.',
};

export class CiviaError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = 'CiviaError';
  }
}

function requestHeaders(options: RequestInit) {
  const headers = new Headers(options.headers);
  if (csrf && !['GET', 'HEAD'].includes(options.method ?? 'GET')) headers.set('X-CSRF-Token', csrf);
  return headers;
}

function deadline(milliseconds: number, parent?: AbortSignal | null) {
  const controller = new AbortController();
  const abort = () => controller.abort();
  if (parent?.aborted) abort();
  else parent?.addEventListener('abort', abort, { once: true });
  const timer = window.setTimeout(abort, milliseconds);
  return {
    signal: controller.signal,
    dispose: () => {
      window.clearTimeout(timer);
      parent?.removeEventListener('abort', abort);
    },
  };
}

async function request(path: string, options: RequestInit = {}, ownerId?: string, installationId?: string): Promise<Response> {
  let response: Response;
  try {
    response = isNative ? await nativeRequest(path, options, ownerId, installationId) : await fetch(path, {
      ...options,
      headers: requestHeaders(options),
      credentials: 'same-origin',
      cache: 'no-store',
      redirect: 'error',
    });
  } catch (error) {
    const code = (error as { code?: string } | null)?.code;
    if (isNative && (code === 'identity' || code === 'unavailable') && !options.signal?.aborted) {
      window.dispatchEvent(new CustomEvent('civia-connection-lost', { detail: code }));
    }
    throw new CiviaError(0, 'No fue posible conectar con CIVIA. Revisa tu conexión.');
  }
  if (!response.ok) {
    if (response.status === 401 && !path.startsWith('/api/auth/')) {
      window.dispatchEvent(new Event('civia-session-expired'));
    }
    throw new CiviaError(response.status, failureMessages[response.status] ??
      'No se pudo completar la operación. Intenta nuevamente.');
  }
  return response;
}

async function json<T>(path: string, options?: RequestInit, ownerId?: string, installationId?: string): Promise<T> {
  const timeout = deadline(40000, options?.signal);
  try {
    const response = await request(path, { ...options, signal: timeout.signal }, ownerId, installationId);
    if (response.status === 204) return undefined as T;
    try { return await response.json() as T; }
    catch { throw new CiviaError(0, 'No se pudo confirmar la respuesta de CIVIA.'); }
  } finally { timeout.dispose(); }
}

function query(path: string, params: Record<string, string | number | boolean | undefined>) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '') search.set(key, String(value));
  }
  const qs = search.toString();
  return qs ? `${path}?${qs}` : path;
}

function body(method: string, value: unknown, headers?: Record<string, string>): RequestInit {
  return { method, headers: { 'Content-Type': 'application/json', ...headers }, body: JSON.stringify(value) };
}

function setSession(session: Session) {
  csrf = isNative ? '' : session.csrf_token ?? '';
  return session.user;
}

export async function readSession(): Promise<User | null> {
  let cached: Session | undefined;
  if (isNative) {
    const selected = nativeProfile();
    if (!selected) return null;
    const secured = (await connection.cachedSession({ profileId: selected.profileId })).json;
    if (!secured || selected.profileId !== nativeProfile()?.profileId) return null;
    try { cached = JSON.parse(secured) as Session; } catch { return null; }
  }
  try {
    return await setSession(await json<Session>('/api/auth/session'));
  } catch (error) {
    if (error instanceof CiviaError && error.status === 401) {
      csrf = '';
      return null;
    }
    if (cached?.user.role === 'CITIZEN' && Date.parse(cached.expires_at) > Date.now() &&
        error instanceof CiviaError && (error.status === 0 || error.status >= 500)) {
      return cached.user;
    }
    throw error;
  }
}

export async function authenticate(mode: 'login' | 'register', values: { email: string; password: string; name?: string }) {
  return setSession(await json<Session>(`/api/auth/${mode}`, body('POST', values)));
}

export async function logout() {
  try { await json<void>('/api/auth/logout', { method: 'POST' }); }
  catch (error) { if (!(error instanceof CiviaError) || error.status !== 401) throw error; }
  csrf = '';
}

const installationIdPattern = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;

async function webInstallation() {
  const timeout = deadline(5000);
  try {
    const meta = await json<{ installation_id: string; protocol: number }>('/api/meta', { signal: timeout.signal });
    if (meta.protocol !== 1 || !installationIdPattern.test(meta.installation_id)) {
      throw new CiviaError(409, 'La instalación de CIVIA no es compatible.');
    }
    return meta.installation_id.toLowerCase();
  } finally { timeout.dispose(); }
}

export async function draftInstallation(ownerId: string) {
  if (isNative) {
    const installationId = nativeProfile()?.installationId;
    if (installationId) return installationId;
    throw new CiviaError(0, 'Selecciona un servidor CIVIA antes de abrir los borradores.');
  }
  const storageKey = `civia-installation:${ownerId}`;
  try {
    const installationId = await webInstallation();
    try { localStorage.setItem(storageKey, installationId); } catch { /* Storage may be disabled. */ }
    return installationId;
  } catch (error) {
    if (error instanceof CiviaError && (error.status === 0 || error.status >= 500)) {
      const cached = localStorage.getItem(storageKey);
      if (cached && installationIdPattern.test(cached)) return cached;
    }
    throw error;
  }
}

export const getStats = () => json<ReportStats>('/api/reports/stats');
export const getPublicStats = () => json<PublicStats>('/api/public/reports/stats');
export const getPublicMap = () => json<Page<PublicMapItem>>('/api/public/reports?limit=100');
export const getReports = (filters: Record<string, string | number | undefined> = {}) => json<Page<ReportItem>>(query('/api/reports', filters));
export const getReportByCode = (code: string) => json<ReportItem>(`/api/reports/by-code/${encodeURIComponent(code.trim())}`);
export const getEvents = (id: string) => json<ReportEventItem[]>(`/api/reports/${encodeURIComponent(id)}/events`);
export async function getEvidence(id: string, kind: 'photo' | 'audio', signal: AbortSignal) {
  const timeout = deadline(40000, signal);
  try {
    const response = await request(`/api/reports/${encodeURIComponent(id)}/${kind}`, { signal: timeout.signal });
    return await response.blob();
  } finally { timeout.dispose(); }
}
export async function submitReport(data: FormData, key: string, ownerId: string, installationId: string) {
  if (!isNative && await webInstallation() !== installationId) {
    throw new CiviaError(409, 'Este borrador pertenece a otra instalación de CIVIA.');
  }
  return json<ReportItem>('/api/reports', {
    method: 'POST',
    headers: { 'Idempotency-Key': key, 'X-Civia-Account': ownerId, 'X-Civia-Installation': installationId },
    body: data,
  }, ownerId, installationId);
}
export const confirmReport = (id: string, category: ReportCategory, severity: ReportSeverity | null, note: string) =>
  json<ReportItem>(`/api/reports/${encodeURIComponent(id)}/confirm`, body('PATCH', { final_category: category, final_severity: severity, human_override_note: note || null }));
export const queryAgent = (question: string) =>
  json<AgentQueryResponse>('/api/agent/query', body('POST', { query: question }, { 'Idempotency-Key': randomId() }));

export const getNotifications = () => json<AdminNotificationsResponse>('/api/admin/notifications?limit=50');
export const markRead = (id: string) => json<void>(`/api/admin/notifications/${encodeURIComponent(id)}/read`, { method: 'PATCH' });
export const markAllRead = () => json<void>('/api/admin/notifications/mark-all-read', { method: 'POST' });
export const getApprovals = (status = 'PENDING', limit = 20, offset = 0) => json<Page<PendingApprovalItem>>(query('/api/admin/approvals', { status, limit, offset }));
export const decideApproval = (id: string, approve: boolean) =>
  json<void>(`/api/admin/approvals/${encodeURIComponent(id)}/decide`, body('POST', { approve }));
export const updateManagement = (id: string, values: { assigned_to?: string; admin_review_status?: string; public_note?: string; internal_note?: string }) =>
  json<ReportItem>(`/api/admin/reports/${encodeURIComponent(id)}/management`, body('POST', values));
export const getInternalNotes = (id: string) =>
  json<{ items: { note: string; created_at: string }[] }>(`/api/admin/reports/${encodeURIComponent(id)}/internal-notes`);
export const updateCaseStatus = (id: string, status: string, note: string) =>
  json<ReportItem>(`/api/reports/${encodeURIComponent(id)}/status`, body('PATCH', { status, human_approved: true, note: note || null }));

export const getUsers = (offset: number, limit: number) => json<Page<User>>(query('/api/admin/users', { offset, limit }));
export const createUser = (values: { name: string; email: string; password: string; role: Role }) =>
  json<User>('/api/admin/users', body('POST', values));
export const updateUser = (id: string, values: { role?: Role; active?: boolean }) =>
  json<User>(`/api/admin/users/${encodeURIComponent(id)}`, body('PATCH', values));
export const resetPassword = (id: string, password: string) =>
  json<void>(`/api/admin/users/${encodeURIComponent(id)}/reset-password`, body('POST', { password }));
export const getAudit = (offset: number, limit: number) => json<Page<AuditEntry>>(query('/api/admin/audit', { offset, limit }));
export const getObservability = () => json<ObservabilityData>('/api/admin/observability?limit=50');
export const setFault = (mode: string) => json<void>('/api/admin/fault-injection', body('POST', { mode, reset_circuits: true }));
export const getQueue = () => json<AnalysisQueue>('/api/admin/queue');
export const getDeadLetters = (offset: number, limit: number) => json<Omit<Page<DeadLetterJob>, 'total'>>(query('/api/admin/queue/dead-letter', { offset, limit }));
export const requeue = (id: string, key: string) =>
  json<void>(`/api/admin/queue/dead-letter/${encodeURIComponent(id)}/requeue`, { method: 'POST', headers: { 'Idempotency-Key': key } });

export const getSystem = () => json<{ status: string; version: string }>('/api/admin/system');
