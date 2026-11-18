CREATE TABLE IF NOT EXISTS analysis_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_id UUID NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
    report_version INTEGER NOT NULL CHECK (report_version > 0),
    state TEXT NOT NULL DEFAULT 'QUEUED' CHECK (state IN
        ('QUEUED', 'PROCESSING', 'RETRY_SCHEDULED', 'COMPLETED', 'DEAD_LETTER', 'CANCELLED')),
    priority SMALLINT NOT NULL DEFAULT 0,
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    max_attempts INTEGER NOT NULL DEFAULT 4 CHECK (max_attempts BETWEEN 1 AND 10),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    available_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    worker_id TEXT,
    lease_expires_at TIMESTAMPTZ,
    fence BIGINT NOT NULL DEFAULT 0,
    last_error TEXT,
    finished_at TIMESTAMPTZ,
    requeue_count INTEGER NOT NULL DEFAULT 0,
    UNIQUE (report_id, report_version),
    CHECK (attempts <= max_attempts),
    CHECK (
        (state = 'PROCESSING' AND worker_id IS NOT NULL AND lease_expires_at IS NOT NULL)
        OR
        (state <> 'PROCESSING' AND worker_id IS NULL AND lease_expires_at IS NULL)
    )
);

CREATE INDEX IF NOT EXISTS analysis_jobs_ready
ON analysis_jobs (priority DESC, available_at, id)
WHERE state IN ('QUEUED', 'RETRY_SCHEDULED');

CREATE INDEX IF NOT EXISTS analysis_jobs_leased
ON analysis_jobs (lease_expires_at) WHERE state = 'PROCESSING';

CREATE INDEX IF NOT EXISTS analysis_jobs_dead_letter
ON analysis_jobs (finished_at DESC, id) WHERE state = 'DEAD_LETTER';

CREATE TABLE IF NOT EXISTS analysis_worker_status (
    singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
    last_seen_at TIMESTAMPTZ NOT NULL
);

-- Esta es la única vía con la que el worker publica un diagnóstico. Se vuelve
-- a evaluar el vencimiento después de esperar el bloqueo de la fila del reporte.
CREATE OR REPLACE FUNCTION civia_publish_analysis(
    job_id UUID, job_fence BIGINT, category TEXT, severity TEXT,
    confidence DOUBLE PRECISION, summary TEXT, keywords JSONB
) RETURNS BOOLEAN
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
    job public.analysis_jobs%ROWTYPE;
    published BOOLEAN;
BEGIN
    SELECT * INTO job FROM public.analysis_jobs
    WHERE id = job_id AND state = 'PROCESSING' AND fence = job_fence
      AND lease_expires_at > clock_timestamp()
    FOR UPDATE;
    IF NOT FOUND THEN
        RETURN FALSE;
    END IF;

    PERFORM id FROM public.reports WHERE id = job.report_id FOR NO KEY UPDATE;
    IF job.lease_expires_at <= clock_timestamp() THEN
        RETURN FALSE;
    END IF;

    UPDATE public.reports
    SET ai_category = category, ai_severity = severity, ai_confidence = confidence,
        ai_summary = summary, ai_keywords = keywords,
        status = 'ANALYZED_PENDING_CONFIRMATION', updated_at = clock_timestamp()
    WHERE id = job.report_id AND version = job.report_version
      AND NOT human_confirmed AND status = 'PENDING_ANALYSIS';
    published := FOUND;

    UPDATE public.analysis_jobs
    SET state = CASE WHEN published THEN 'COMPLETED' ELSE 'CANCELLED' END,
        worker_id = NULL, lease_expires_at = NULL,
        last_error = NULL, finished_at = clock_timestamp()
    WHERE id = job.id;

    IF published THEN
        INSERT INTO public.report_events (
            report_id, event_type, previous_status, new_status, public_message, actor_type
        ) VALUES (
            job.report_id, 'AI_ANALYSIS_COMPLETED', 'PENDING_ANALYSIS',
            'ANALYZED_PENDING_CONFIRMATION', 'El análisis preliminar está disponible.', 'SYSTEM'
        );
    END IF;

    RETURN published;
END;
$$;

REVOKE EXECUTE ON FUNCTION civia_publish_analysis(UUID, BIGINT, TEXT, TEXT, DOUBLE PRECISION, TEXT, JSONB) FROM PUBLIC;

CREATE OR REPLACE FUNCTION civia_lock_analysis_report(requested_job UUID)
RETURNS TABLE (
    tracking_code VARCHAR(32), is_synthetic BOOLEAN, human_confirmed BOOLEAN,
    status VARCHAR(32), version INTEGER
)
LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, pg_temp
AS $$
    SELECT r.tracking_code, r.is_synthetic, r.human_confirmed, r.status, r.version
    FROM public.reports r JOIN public.analysis_jobs j ON j.report_id = r.id
    WHERE j.id = requested_job AND j.state = 'PROCESSING'
    FOR SHARE OF r
$$;

REVOKE EXECUTE ON FUNCTION civia_lock_analysis_report(UUID) FROM PUBLIC;
