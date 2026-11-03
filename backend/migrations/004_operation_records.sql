-- 004_operation_records.sql
-- G2.1.6: Contrato transaccional A-02 y registro durable de operaciones (COMMITTED, ABORTED, PENDING, UNKNOWN)

CREATE TABLE IF NOT EXISTS operation_records (
    operation_id UUID PRIMARY KEY,
    idempotency_key VARCHAR(128) UNIQUE,
    operation_type VARCHAR(64) NOT NULL,
    target_id VARCHAR(128),
    status VARCHAR(32) NOT NULL CHECK (status IN ('PENDING', 'COMMITTED', 'ABORTED', 'UNKNOWN')),
    proposed_payload JSONB,
    result_payload JSONB,
    error_message TEXT,
    backend_pid INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX IF NOT EXISTS idx_operation_records_status
    ON operation_records (status);

CREATE INDEX IF NOT EXISTS idx_operation_records_idempotency
    ON operation_records (idempotency_key)
    WHERE idempotency_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_operation_records_target
    ON operation_records (target_id)
    WHERE target_id IS NOT NULL;
