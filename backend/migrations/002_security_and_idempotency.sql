-- 002_security_and_idempotency.sql
-- Bloque G1: Credencial por reporte (edit_token_hash), idempotencia durable (idempotency_key) y versión de fila

ALTER TABLE reports ADD COLUMN IF NOT EXISTS edit_token_hash VARCHAR(64);
ALTER TABLE reports ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR(128);
ALTER TABLE reports ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1;

CREATE UNIQUE INDEX IF NOT EXISTS uq_reports_idempotency_key
    ON reports (idempotency_key)
    WHERE idempotency_key IS NOT NULL;

CREATE TABLE IF NOT EXISTS idempotency_records (
    idempotency_key VARCHAR(128) PRIMARY KEY,
    request_fingerprint VARCHAR(64) NOT NULL,
    report_id UUID NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
    tracking_code VARCHAR(32),
    citizen_edit_token VARCHAR(128),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE idempotency_records ADD COLUMN IF NOT EXISTS tracking_code VARCHAR(32);
ALTER TABLE idempotency_records ADD COLUMN IF NOT EXISTS citizen_edit_token VARCHAR(128);

CREATE INDEX IF NOT EXISTS idx_idempotency_records_report_id
    ON idempotency_records (report_id);
