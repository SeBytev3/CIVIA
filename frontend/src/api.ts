import type {
  AgentQueryResponse,
  ObservabilityData,
  PendingApprovalItem,
  ReportCategory,
  ReportItem,
  ReportListResponse,
  ReportSeverity,
  ReportStats,
} from './types';

const API_BASE = import.meta.env.VITE_API_BASE_URL || '';

async function safeJsonFetch<T>(url: string, options?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${url}`, options);
  } catch {
    throw new Error(
      'No fue posible conectar con el servicio de CIVIA. Verifique su conexión e intente nuevamente.'
    );
  }

  if (!response.ok) {
    let userMessage = 'No se pudo completar la operación solicitada. Intente nuevamente.';
    try {
      const errBody = await response.json();
      if (errBody && typeof errBody.message === 'string') {
        userMessage = errBody.message;
      }
    } catch {
      // Ignorar errores de parseo para nunca mostrar detalles internos HTTP al ciudadano
    }
    throw new Error(userMessage);
  }

  return (await response.json()) as T;
}

export async function fetchStats(): Promise<ReportStats> {
  return safeJsonFetch<ReportStats>('/api/reports/stats');
}

export async function fetchReports(params: {
  category?: string;
  severity?: string;
  status?: string;
  comuna?: string;
  q?: string;
  lat?: number;
  lon?: number;
  radius_km?: number;
  limit?: number;
}): Promise<ReportListResponse> {
  const sp = new URLSearchParams();
  if (params.category) sp.set('category', params.category);
  if (params.severity) sp.set('severity', params.severity);
  if (params.status) sp.set('status', params.status);
  if (params.comuna) sp.set('comuna', params.comuna);
  if (params.q) sp.set('q', params.q);
  if (params.lat !== undefined) sp.set('lat', String(params.lat));
  if (params.lon !== undefined) sp.set('lon', String(params.lon));
  if (params.radius_km !== undefined) sp.set('radius_km', String(params.radius_km));
  if (params.limit !== undefined) sp.set('limit', String(params.limit));

  const qs = sp.toString();
  return safeJsonFetch<ReportListResponse>(`/api/reports${qs ? `?${qs}` : ''}`);
}

export async function fetchReportByCode(trackingCode: string): Promise<ReportItem> {
  return safeJsonFetch<ReportItem>(
    `/api/reports/by-code/${encodeURIComponent(trackingCode.trim())}`
  );
}

export async function fetchReportById(reportId: string): Promise<ReportItem> {
  return safeJsonFetch<ReportItem>(`/api/reports/${encodeURIComponent(reportId)}`);
}

export async function submitCitizenReport(
  formData: FormData,
  idempotencyKey?: string
): Promise<ReportItem> {
  const opKey =
    idempotencyKey ||
    (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
      ? `civia-op-${crypto.randomUUID()}`
      : `civia-op-${Date.now()}-${Math.random().toString(36).slice(2)}`);
  return safeJsonFetch<ReportItem>('/api/reports', {
    method: 'POST',
    headers: { 'Idempotency-Key': opKey },
    body: formData,
  });
}

export async function triggerReportAnalysis(reportId: string): Promise<ReportItem> {
  return safeJsonFetch<ReportItem>(`/api/reports/${encodeURIComponent(reportId)}/analyze`, {
    method: 'POST',
  });
}

export async function confirmReportClassification(
  reportId: string,
  payload: {
    final_category: ReportCategory;
    final_severity: ReportSeverity;
    human_override_note?: string;
    edit_token?: string;
  },
  citizenEditToken?: string | null,
  adminToken?: string | null
): Promise<ReportItem> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  const tok = citizenEditToken || payload.edit_token;
  if (tok) {
    headers['X-Citizen-Edit-Token'] = tok;
  }
  if (adminToken && adminToken.trim()) {
    headers['X-Admin-Token'] = adminToken.trim();
  }
  return safeJsonFetch<ReportItem>(`/api/reports/${encodeURIComponent(reportId)}/confirm`, {
    method: 'PATCH',
    headers,
    body: JSON.stringify(payload),
  });
}

export async function queryAgent(payload: {
  query: string;
  max_iterations?: number;
  max_tokens_budget?: number;
}): Promise<AgentQueryResponse> {
  return safeJsonFetch<AgentQueryResponse>('/api/agent/query', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export async function fetchAdminObservability(adminToken: string): Promise<ObservabilityData> {
  return safeJsonFetch<ObservabilityData>('/api/admin/observability?limit=60', {
    headers: { 'X-Admin-Token': adminToken },
  });
}

export async function setAdminFaultInjection(
  adminToken: string,
  mode: string
): Promise<{ effective_fault_mode: string }> {
  return safeJsonFetch<{ effective_fault_mode: string }>('/api/admin/fault-injection', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Admin-Token': adminToken,
    },
    body: JSON.stringify({ mode, reset_circuits: true }),
  });
}

export async function fetchAdminApprovals(
  adminToken: string
): Promise<{ total: number; items: PendingApprovalItem[] }> {
  return safeJsonFetch<{ total: number; items: PendingApprovalItem[] }>('/api/admin/approvals', {
    headers: { 'X-Admin-Token': adminToken },
  });
}

export async function decideAdminApproval(
  adminToken: string,
  approvalId: string,
  approve: boolean,
  decidedBy: string
): Promise<void> {
  await safeJsonFetch(`/api/admin/approvals/${encodeURIComponent(approvalId)}/decide`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Admin-Token': adminToken,
    },
    body: JSON.stringify({ approve, decided_by: decidedBy }),
  });
}
