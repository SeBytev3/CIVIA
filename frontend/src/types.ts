export type ReportCategory = 'HUECO' | 'BASURAS' | 'TALA' | 'QUEMA' | 'OTRO';
export type ReportSeverity = 'BAJA' | 'MEDIA' | 'ALTA' | 'CRITICA';
export type ReportStatus =
  | 'PENDING_ANALYSIS'
  | 'ANALYZED_PENDING_CONFIRMATION'
  | 'CONFIRMED'
  | 'IN_REVIEW'
  | 'RESOLVED'
  | 'REJECTED';

export interface ReportItem {
  id: string;
  tracking_code: string;
  title: string;
  description: string;
  latitude: number;
  longitude: number;
  in_service_area: boolean;
  comuna: string | null;
  neighborhood: string | null;
  address_hint: string | null;
  photo_url: string;
  photo_mime: string;
  photo_width: number;
  photo_height: number;
  has_audio: boolean;
  audio_transcript: string | null;
  ai_category: ReportCategory | null;
  ai_severity: ReportSeverity | null;
  ai_confidence: number | null;
  ai_summary: string | null;
  ai_keywords: string[];
  final_category: ReportCategory | null;
  final_severity: ReportSeverity | null;
  effective_category: ReportCategory | null;
  effective_severity: ReportSeverity | null;
  human_confirmed: boolean;
  human_override_note: string | null;
  status: ReportStatus;
  status_message: string;
  analysis_status?: AnalysisStatus;
  analysis_status_message?: string;
  analysis_delayed?: boolean;
  distance_km: number | null;
  is_synthetic: boolean;
  citizen_edit_token?: string | null;
  assigned_to?: string | null;
  assigned_at?: string | null;
  external_delivery_status?: string;
  external_delivery_channel?: string;
  external_delivery_message?: string;
  admin_review_status?: string;
  last_public_note?: string | null;
  events?: ReportEventItem[];
  created_at: string;
  updated_at: string;
}

export interface ReportListResponse {
  total: number;
  limit: number;
  offset: number;
  items: ReportItem[];
}

export interface ReportStats {
  total_reports: number;
  by_category: Record<string, number>;
  by_status: Record<string, number>;
  by_comuna: Record<string, number>;
  by_assignee?: Record<string, number>;
}

export interface PublicStats {
  total: number;
  by_category: Record<string, number>;
  by_status: Record<string, number>;
  by_severity: Record<string, number>;
}

export interface AgentQueryResponse {
  answer: string;
  requires_human_approval: boolean;
  pending_approval_id: string | null;
  operation_id?: string | null;
  operation_status?: string | null;
}

export interface ObservabilityData {
  provider_chain: Array<{
    tier: string;
    provider: string;
    model: string;
    configured: boolean;
  }>;
  circuit_breakers: Array<{
    provider: string;
    model: string;
    state: string;
    failures: number;
    last_error: string | null;
  }>;
  effective_fault_mode: string;
  observability: {
    metrics: {
      total_trace_events: number;
      successful_events: number;
      failed_events: number;
      success_rate_pct: number;
      p50_latency_ms: number;
      p90_latency_ms: number;
      p50_success_latency_ms: number;
      p90_success_latency_ms: number;
      total_tokens: number;
      total_estimated_cost_usd: number;
      avg_cost_per_event_usd: number;
    };
    by_provider_model: Array<{
      provider: string;
      model: string;
      calls: number;
      successes: number;
      failures: number;
      tokens: number;
    }>;
    recent_traces: Array<{
      id: string;
      report_id: string | null;
      trace_group_id: string;
      operation: string;
      provider: string;
      model: string;
      attempt_number: number;
      success: boolean;
      latency_ms: number;
      total_tokens: number;
      estimated_cost_usd: number;
      error_code: string | null;
      error_detail: string | null;
      created_at: string;
    }>;
  };
}

export interface PendingApprovalItem {
  id: string;
  report_id: string;
  tracking_code: string;
  title: string;
  current_report_status: string;
  proposed_action: string;
  proposed_payload: {
    tracking_code?: string;
    previous_status?: string;
    proposed_status?: string;
  };
  reason: string;
  status: 'PENDING' | 'APPROVED' | 'REJECTED' | 'EXPIRED';
  decided_by: string | null;
  decided_at: string | null;
  created_at: string;
}

export interface ReportEventItem {
  id: string;
  report_id: string;
  event_type: string;
  previous_status: string | null;
  new_status: string | null;
  public_message: string;
  actor_type: 'CITIZEN' | 'ADMIN' | 'SYSTEM';
  created_at: string;
}

export interface AdminNotificationItem {
  id: string;
  report_id: string;
  tracking_code: string;
  title: string;
  message: string;
  is_read: boolean;
  is_synthetic: boolean;
  read_at: string | null;
  created_at: string;
  photo_url?: string | null;
  category?: string | null;
  status?: string | null;
  neighborhood?: string | null;
}

export interface AdminNotificationsResponse {
  total: number;
  unread_total: number;
  unread_citizen: number;
  unread_synthetic: number;
  items: AdminNotificationItem[];
}

export type AnalysisStatus = 'PENDING' | 'PROCESSING' | 'AVAILABLE' | 'MANUAL_REVIEW';
export type Role = 'CITIZEN' | 'CASE_ADMIN' | 'WEB_ADMIN';

export interface User {
  id: string;
  name: string;
  email: string;
  role: Role;
  active: boolean;
  created_at: string;
}
export interface Session {
  user: User;
  csrf_token?: string | null;
  token?: string | null;
  expires_at: string;
}
export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}
export interface PublicMapItem {
  latitude: number;
  longitude: number;
  category: ReportCategory | null;
  severity: ReportSeverity | null;
  status: ReportStatus;
}
export interface AuditEntry {
  id: number;
  actor_id?: string | null;
  actor_user_id?: string | null;
  target_id?: string | null;
  target_user_id?: string | null;
  action: string;
  created_at: string;
}
export interface AnalysisQueue {
  counts: Record<string, number>;
  oldest_pending_seconds: number | null;
  worker_available: boolean;
}
export interface DeadLetterJob {
  id: string;
  report_id: string;
  tracking_code: string;
  attempts: number;
  max_attempts: number;
  last_error: string | null;
  finished_at: string | null;
}
