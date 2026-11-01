-- 001_initial_schema.sql
-- Esquema relacional principal de CIVIA (PostgreSQL 17)
-- Estrategia de datos: SQL directo con índices B-Tree y filtro espacial Haversine (sin RAG ni PostGIS pesado)

CREATE TABLE IF NOT EXISTS schema_migrations (
    version VARCHAR(64) PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS reports (
    id UUID PRIMARY KEY,
    tracking_code VARCHAR(32) UNIQUE NOT NULL,
    title VARCHAR(160) NOT NULL,
    description TEXT NOT NULL,
    latitude DOUBLE PRECISION NOT NULL CHECK (latitude >= -90.0 AND latitude <= 90.0),
    longitude DOUBLE PRECISION NOT NULL CHECK (longitude >= -180.0 AND longitude <= 180.0),
    in_service_area BOOLEAN NOT NULL DEFAULT TRUE,
    comuna VARCHAR(64),
    neighborhood VARCHAR(120),
    address_hint VARCHAR(255),
    photo_path VARCHAR(512) NOT NULL,
    photo_mime VARCHAR(64) NOT NULL,
    photo_size_bytes INTEGER NOT NULL CHECK (photo_size_bytes > 0 AND photo_size_bytes <= 5242880),
    photo_width INTEGER NOT NULL CHECK (photo_width >= 32 AND photo_width <= 8192),
    photo_height INTEGER NOT NULL CHECK (photo_height >= 32 AND photo_height <= 8192),
    photo_sha256 VARCHAR(64) NOT NULL,
    audio_path VARCHAR(512),
    audio_mime VARCHAR(64),
    audio_size_bytes INTEGER CHECK (audio_size_bytes IS NULL OR (audio_size_bytes > 0 AND audio_size_bytes <= 5242880)),
    audio_duration_seconds DOUBLE PRECISION CHECK (audio_duration_seconds IS NULL OR (audio_duration_seconds > 0 AND audio_duration_seconds <= 60.0)),
    audio_transcript TEXT,
    ai_category VARCHAR(32) CHECK (ai_category IS NULL OR ai_category IN ('HUECO', 'BASURAS', 'TALA', 'QUEMA', 'OTRO')),
    ai_severity VARCHAR(16) CHECK (ai_severity IS NULL OR ai_severity IN ('BAJA', 'MEDIA', 'ALTA', 'CRITICA')),
    ai_confidence DOUBLE PRECISION CHECK (ai_confidence IS NULL OR (ai_confidence >= 0.0 AND ai_confidence <= 1.0)),
    ai_summary VARCHAR(500),
    ai_keywords JSONB NOT NULL DEFAULT '[]'::jsonb,
    final_category VARCHAR(32) CHECK (final_category IS NULL OR final_category IN ('HUECO', 'BASURAS', 'TALA', 'QUEMA', 'OTRO')),
    final_severity VARCHAR(16) CHECK (final_severity IS NULL OR final_severity IN ('BAJA', 'MEDIA', 'ALTA', 'CRITICA')),
    human_confirmed BOOLEAN NOT NULL DEFAULT FALSE,
    human_override_note TEXT,
    status VARCHAR(32) NOT NULL DEFAULT 'PENDING_ANALYSIS' CHECK (
        status IN (
            'PENDING_ANALYSIS',
            'ANALYZED_PENDING_CONFIRMATION',
            'CONFIRMED',
            'IN_REVIEW',
            'RESOLVED',
            'REJECTED'
        )
    ),
    is_synthetic BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_reports_coords ON reports (latitude, longitude);
CREATE INDEX IF NOT EXISTS idx_reports_status ON reports (status);
CREATE INDEX IF NOT EXISTS idx_reports_final_category ON reports (final_category);
CREATE INDEX IF NOT EXISTS idx_reports_ai_category ON reports (ai_category);
CREATE INDEX IF NOT EXISTS idx_reports_created_at ON reports (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_reports_comuna ON reports (comuna);

CREATE TABLE IF NOT EXISTS ai_traces (
    id UUID PRIMARY KEY,
    report_id UUID REFERENCES reports(id) ON DELETE SET NULL,
    trace_group_id UUID NOT NULL,
    operation VARCHAR(64) NOT NULL,
    provider VARCHAR(32) NOT NULL,
    model VARCHAR(128) NOT NULL,
    attempt_number INTEGER NOT NULL DEFAULT 1,
    success BOOLEAN NOT NULL,
    latency_ms INTEGER NOT NULL CHECK (latency_ms >= 0),
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    estimated_cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    error_code VARCHAR(64),
    error_detail TEXT,
    tool_calls JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ai_traces_report_id ON ai_traces (report_id);
CREATE INDEX IF NOT EXISTS idx_ai_traces_created_at ON ai_traces (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_traces_operation ON ai_traces (operation);

CREATE TABLE IF NOT EXISTS pending_approvals (
    id UUID PRIMARY KEY,
    report_id UUID NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
    proposed_action VARCHAR(64) NOT NULL,
    proposed_payload JSONB NOT NULL,
    reason TEXT NOT NULL,
    requested_by_agent VARCHAR(64) NOT NULL DEFAULT 'civia-agent',
    status VARCHAR(32) NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED')),
    decided_by VARCHAR(128),
    decided_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pending_approvals_status ON pending_approvals (status);
CREATE INDEX IF NOT EXISTS idx_pending_approvals_report_id ON pending_approvals (report_id);
