ALTER TABLE reports ADD COLUMN IF NOT EXISTS audio_sha256 VARCHAR(64)
    CHECK (audio_sha256 ~ '^[a-f0-9]{64}$');

CREATE OR REPLACE FUNCTION civia_publish_analysis_with_audio(
    job_id UUID, job_fence BIGINT, category TEXT, severity TEXT,
    confidence DOUBLE PRECISION, summary TEXT, keywords JSONB, transcript TEXT
) RETURNS BOOLEAN
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
    published BOOLEAN;
BEGIN
    published := public.civia_publish_analysis(
        job_id, job_fence, category, severity, confidence, summary, keywords
    );
    -- El diagnóstico ya ha bloqueado la fila y validado la versión en esta
    -- misma transacción. La voz es opcional y tiene su propia huella.
    IF published AND transcript IS NOT NULL THEN
        UPDATE public.reports r SET audio_transcript = LEFT(transcript, 600)
        FROM public.analysis_jobs j
        WHERE j.id = job_id AND j.report_id = r.id AND r.audio_sha256 IS NOT NULL;
    END IF;
    RETURN published;
END;
$$;

REVOKE EXECUTE ON FUNCTION civia_publish_analysis_with_audio(UUID, BIGINT, TEXT, TEXT, DOUBLE PRECISION, TEXT, JSONB, TEXT)
    FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION civia_publish_analysis(UUID, BIGINT, TEXT, TEXT, DOUBLE PRECISION, TEXT, JSONB)
    FROM civia_worker;
GRANT EXECUTE ON FUNCTION civia_publish_analysis_with_audio(UUID, BIGINT, TEXT, TEXT, DOUBLE PRECISION, TEXT, JSONB, TEXT)
    TO civia_worker;
GRANT SELECT (audio_path, audio_mime, audio_size_bytes, audio_sha256) ON reports TO civia_worker;
