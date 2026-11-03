-- 005_operation_records_hardening.sql
-- G2.1.7: Endurecimiento fail-closed, autorizacion, evidencia y alcance de idempotencia

-- 1. Agregar columnas a operation_records
ALTER TABLE operation_records
    ADD COLUMN IF NOT EXISTS requester_id VARCHAR(128) NOT NULL DEFAULT 'citizen',
    ADD COLUMN IF NOT EXISTS payload_hash VARCHAR(64),
    ADD COLUMN IF NOT EXISTS query_token_hash VARCHAR(64);

-- 2. Eliminar restriccion unica global previa de idempotency_key si existe para permitir alcance compuesto
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'operation_records_idempotency_key_key'
    ) THEN
        ALTER TABLE operation_records DROP CONSTRAINT operation_records_idempotency_key_key;
    END IF;
END $$;

-- 3. Crear restriccion unica por ambito (requester_id, operation_type, idempotency_key)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'uq_operation_records_scoped'
    ) THEN
        ALTER TABLE operation_records
            ADD CONSTRAINT uq_operation_records_scoped
            UNIQUE (requester_id, operation_type, idempotency_key);
    END IF;
END $$;

-- 4. Vincular pending_approvals con operation_id de forma explicita e indexada
ALTER TABLE pending_approvals
    ADD COLUMN IF NOT EXISTS operation_id UUID REFERENCES operation_records(operation_id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_pending_approvals_operation_id
    ON pending_approvals (operation_id)
    WHERE operation_id IS NOT NULL;

-- 5. Prevenir propuestas de actualizacion duplicadas concurrentes en estado PENDING para el mismo reporte
CREATE UNIQUE INDEX IF NOT EXISTS idx_pending_approvals_active_proposal
    ON pending_approvals (report_id)
    WHERE status = 'PENDING' AND proposed_action = 'UPDATE_REPORT_STATUS';
