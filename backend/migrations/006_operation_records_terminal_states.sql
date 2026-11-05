-- 006_operation_records_terminal_states.sql
-- G2.1.8: Inmutabilidad estricta de estados terminales en operation_records

CREATE OR REPLACE FUNCTION prevent_terminal_operation_state_mutation()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.status IN ('COMMITTED', 'ABORTED') AND NEW.status != OLD.status THEN
        RAISE EXCEPTION 'Operacion % en estado terminal % no puede transicionar a %', OLD.operation_id, OLD.status, NEW.status;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'trg_prevent_terminal_operation_state_mutation'
    ) THEN
        CREATE TRIGGER trg_prevent_terminal_operation_state_mutation
            BEFORE UPDATE ON operation_records
            FOR EACH ROW
            EXECUTE FUNCTION prevent_terminal_operation_state_mutation();
    END IF;
END $$;
