-- La marca única anterior era efímera. Conservar una por proceso permite
-- mostrar circuitos independientes cuando se ejecuta más de un worker.
DELETE FROM analysis_worker_status;
ALTER TABLE analysis_worker_status
    DROP COLUMN singleton,
    ADD COLUMN worker_id TEXT PRIMARY KEY,
    ADD COLUMN circuits JSONB NOT NULL DEFAULT '[]'::jsonb;
CREATE INDEX analysis_worker_status_seen ON analysis_worker_status (last_seen_at);
GRANT DELETE ON analysis_worker_status TO civia_worker;

CREATE INDEX analysis_jobs_completed ON analysis_jobs (finished_at DESC) WHERE state = 'COMPLETED';

CREATE OR REPLACE FUNCTION civia_worker_job_evidence(job_id UUID, job_fence BIGINT)
RETURNS TABLE (
    description TEXT, latitude DOUBLE PRECISION, longitude DOUBLE PRECISION,
    photo_path VARCHAR(512), photo_mime VARCHAR(64), photo_sha256 VARCHAR(64), photo_size_bytes INTEGER,
    audio_path VARCHAR(512), audio_mime VARCHAR(64), audio_size_bytes INTEGER, audio_sha256 VARCHAR(64)
)
LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, pg_temp
AS $$
    SELECT r.description, r.latitude, r.longitude, r.photo_path, r.photo_mime,
           r.photo_sha256, r.photo_size_bytes, r.audio_path, r.audio_mime, r.audio_size_bytes, r.audio_sha256
    FROM public.reports r JOIN public.analysis_jobs j ON j.report_id = r.id
    WHERE j.id = job_id AND j.fence = job_fence AND j.state = 'PROCESSING'
      AND j.lease_expires_at > clock_timestamp()
      AND r.version = j.report_version AND NOT r.human_confirmed AND r.status = 'PENDING_ANALYSIS'
$$;

REVOKE EXECUTE ON FUNCTION civia_worker_job_evidence(UUID, BIGINT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION civia_worker_job_evidence(UUID, BIGINT) TO civia_worker;
REVOKE SELECT (id, version, status, human_confirmed, description, latitude, longitude,
    photo_path, photo_mime, photo_sha256, photo_size_bytes, audio_path, audio_mime,
    audio_size_bytes, audio_sha256) ON reports FROM civia_worker;
