DO $$
DECLARE runtime_role TEXT;
BEGIN
    FOREACH runtime_role IN ARRAY ARRAY['civia_app', 'civia_agent', 'civia_worker']
    LOOP
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = runtime_role) THEN
            BEGIN
                EXECUTE format('CREATE ROLE %I NOLOGIN NOINHERIT', runtime_role);
            EXCEPTION WHEN duplicate_object OR unique_violation THEN
                NULL;
            END;
        END IF;
    END LOOP;
    EXECUTE format('REVOKE TEMPORARY ON DATABASE %I FROM PUBLIC', current_database());
END;
$$;

REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM PUBLIC;
ALTER DEFAULT PRIVILEGES REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;

GRANT USAGE ON SCHEMA public TO civia_app, civia_agent, civia_worker;

GRANT SELECT, INSERT, UPDATE, DELETE ON reports TO civia_app;
GRANT SELECT, INSERT ON report_events, idempotency_records, report_internal_notes TO civia_app;
GRANT SELECT, INSERT, UPDATE ON operation_records, pending_approvals, admin_notifications,
    users, analysis_jobs TO civia_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON auth_sessions, auth_rate_limits TO civia_app;
GRANT SELECT, INSERT ON ai_traces, security_audit TO civia_app;
GRANT USAGE ON SEQUENCE security_audit_id_seq TO civia_app;
GRANT SELECT ON analysis_worker_status TO civia_app;

CREATE OR REPLACE VIEW agent_reports WITH (security_barrier = true) AS
SELECT id, owner_id, is_synthetic, tracking_code, status, version,
       COALESCE(final_category, ai_category) AS category,
       COALESCE(final_severity, ai_severity) AS severity, comuna, created_at
FROM reports
WHERE (is_synthetic AND owner_id IS NULL)
   OR owner_id = NULLIF(current_setting('civia.agent_owner', true), '')::uuid;

REVOKE ALL ON agent_reports FROM PUBLIC;
GRANT SELECT ON agent_reports TO civia_agent;

GRANT SELECT ON analysis_jobs TO civia_worker;
GRANT UPDATE (state, attempts, worker_id, lease_expires_at, fence, last_error, available_at, finished_at)
    ON analysis_jobs TO civia_worker;
GRANT SELECT, INSERT, UPDATE ON analysis_worker_status TO civia_worker;
GRANT SELECT (id, version, status, human_confirmed, description, latitude, longitude,
    photo_path, photo_mime, photo_sha256, photo_size_bytes) ON reports TO civia_worker;
GRANT INSERT ON ai_traces, report_events TO civia_worker;
GRANT SELECT (report_id), INSERT (report_id, title, message, is_synthetic),
    UPDATE (title, message, is_read, read_at, created_at) ON admin_notifications TO civia_worker;
GRANT SELECT (title, message) ON admin_notifications TO civia_worker;
GRANT EXECUTE ON FUNCTION civia_publish_analysis(UUID, BIGINT, TEXT, TEXT, DOUBLE PRECISION, TEXT, JSONB)
    TO civia_worker;
GRANT EXECUTE ON FUNCTION civia_lock_analysis_report(UUID) TO civia_worker;
