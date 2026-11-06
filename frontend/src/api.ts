import type {
  
  AdminNotificationsResponse,
  AgentQueryResponse,
  ObservabilityData,
  OperationStatusResponse,
  PendingApprovalItem,
  ReportCategory,
  ReportEventItem,
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
  operation_token?: string;
  idempotency_key?: string;
}): Promise<AgentQueryResponse> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (payload.operation_token) {
    headers['X-Operation-Token'] = payload.operation_token;
  }
  if (payload.idempotency_key) {
    headers['Idempotency-Key'] = payload.idempotency_key;
  }
  return safeJsonFetch<AgentQueryResponse>('/api/agent/query', {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
  });
}

export async function getOperationStatus(
  operationId: string,
  operationToken?: string,
  adminToken?: string,
): Promise<OperationStatusResponse> {
  const headers: Record<string, string> = {};
  if (operationToken) {
    headers['X-Operation-Token'] = operationToken;
  }
  if (adminToken) {
    headers['X-Admin-Token'] = adminToken;
  }
  return safeJsonFetch<OperationStatusResponse>(`/api/operations/${encodeURIComponent(operationId)}`, {
    headers,
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

export async function fetchReportEvents(
  identifier: string,
  byTrackingCode: boolean = false
): Promise<ReportEventItem[]> {
  const url = byTrackingCode
    ? `/api/reports/by-code/${encodeURIComponent(identifier.trim())}/events`
    : `/api/reports/${encodeURIComponent(identifier.trim())}/events`;
  return safeJsonFetch<ReportEventItem[]>(url);
}

export async function fetchAdminNotifications(
  adminToken: string,
  options?: { limit?: number; unread_only?: boolean; filter_type?: string }
): Promise<AdminNotificationsResponse> {
  const sp = new URLSearchParams();
  if (options?.limit) sp.set('limit', String(options.limit));
  if (options?.unread_only) sp.set('unread_only', 'true');
  if (options?.filter_type) sp.set('filter_type', options.filter_type);
  const qs = sp.toString();
  return safeJsonFetch<AdminNotificationsResponse>(
    `/api/admin/notifications${qs ? `?${qs}` : ''}`,
    {
      headers: { 'X-Admin-Token': adminToken.trim() },
    }
  );
}

export async function markAdminNotificationRead(
  adminToken: string,
  notificationId: string
): Promise<void> {
  await safeJsonFetch(
    `/api/admin/notifications/${encodeURIComponent(notificationId)}/read`,
    {
      method: 'PATCH',
      headers: { 'X-Admin-Token': adminToken.trim() },
    }
  );
}

export async function markAllAdminNotificationsRead(
  adminToken: string
): Promise<{ updated_count: number }> {
  return safeJsonFetch<{ updated_count: number }>(
    '/api/admin/notifications/mark-all-read',
    {
      method: 'POST',
      headers: { 'X-Admin-Token': adminToken.trim() },
    }
  );
}

export async function updateReportManagement(
  adminToken: string,
  reportId: string,
  payload: {
    assigned_to?: string;
    admin_review_status?: string;
    public_note?: string;
  }
): Promise<ReportItem> {
  return safeJsonFetch<ReportItem>(
    `/api/admin/reports/${encodeURIComponent(reportId)}/management`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Admin-Token': adminToken.trim(),
      },
      body: JSON.stringify(payload),
    }
  );
}
