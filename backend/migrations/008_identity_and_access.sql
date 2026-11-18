CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(120) NOT NULL,
    email VARCHAR(254) UNIQUE NOT NULL CHECK (email = lower(email)),
    password_hash TEXT NOT NULL CHECK (password_hash LIKE '$argon2id$%'),
    role VARCHAR(16) NOT NULL CHECK (role IN ('CITIZEN', 'CASE_ADMIN', 'WEB_ADMIN')),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_active_web_admin ON users (id)
    WHERE role = 'WEB_ADMIN' AND active;

CREATE TABLE IF NOT EXISTS auth_sessions (
    token_hash BYTEA PRIMARY KEY CHECK (octet_length(token_hash) = 32),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    mode VARCHAR(6) NOT NULL CHECK (mode IN ('cookie', 'bearer')),
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_auth_sessions_user ON auth_sessions (user_id)
    WHERE revoked_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_auth_sessions_expiry ON auth_sessions (expires_at);

CREATE TABLE IF NOT EXISTS auth_rate_limits (
    bucket BYTEA PRIMARY KEY CHECK (octet_length(bucket) = 32),
    attempts INTEGER NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_auth_rate_limits_expiry ON auth_rate_limits (expires_at);

CREATE TABLE IF NOT EXISTS security_audit (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    actor_id UUID REFERENCES users(id),
    action VARCHAR(64) NOT NULL,
    target_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_security_audit_order ON security_audit (created_at DESC, id DESC);

ALTER TABLE reports ADD COLUMN IF NOT EXISTS owner_id UUID REFERENCES users(id);
CREATE INDEX IF NOT EXISTS idx_reports_owner_created_at ON reports (owner_id, created_at DESC)
    WHERE owner_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS report_internal_notes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_id UUID NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
    actor_id UUID REFERENCES users(id),
    note TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_report_internal_notes_report
    ON report_internal_notes (report_id, created_at DESC, id DESC);

INSERT INTO report_internal_notes (report_id, note, created_at)
SELECT id, admin_internal_notes, updated_at
FROM reports r
WHERE NULLIF(BTRIM(admin_internal_notes), '') IS NOT NULL
    AND NOT EXISTS (SELECT 1 FROM report_internal_notes n WHERE n.report_id = r.id);
