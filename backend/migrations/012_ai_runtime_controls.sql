CREATE TABLE ai_runtime_settings (
    singleton boolean PRIMARY KEY DEFAULT TRUE CHECK (singleton),
    fault_mode text NOT NULL DEFAULT '',
    updated_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO ai_runtime_settings (singleton) VALUES (TRUE);

CREATE TABLE ai_quota_windows (
    scope text NOT NULL,
    window_start timestamptz NOT NULL,
    calls integer NOT NULL CHECK (calls >= 0),
    estimated_tokens bigint NOT NULL CHECK (estimated_tokens >= 0),
    PRIMARY KEY (scope, window_start)
);
CREATE INDEX ai_quota_windows_expiry ON ai_quota_windows (window_start);

CREATE TABLE ai_validated_models (
    provider text NOT NULL,
    model text NOT NULL,
    capability text NOT NULL,
    credential_fingerprint text NOT NULL,
    validated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (provider, model, capability)
);

DO $$
BEGIN
    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'civia_app') THEN
        GRANT SELECT, UPDATE ON ai_runtime_settings TO civia_app;
        GRANT SELECT, INSERT, UPDATE, DELETE ON ai_quota_windows TO civia_app;
        GRANT SELECT, INSERT, UPDATE, DELETE ON ai_validated_models TO civia_app;
    END IF;
    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'civia_worker') THEN
        GRANT SELECT ON ai_runtime_settings TO civia_worker;
        GRANT SELECT, INSERT, UPDATE, DELETE ON ai_quota_windows TO civia_worker;
        GRANT SELECT ON ai_validated_models TO civia_worker;
    END IF;
END $$;
