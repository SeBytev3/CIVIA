-- 007_report_events_and_admin_notifications.sql
-- Trazabilidad de eventos de reportes ciudadanos y notificaciones administrativas internas

-- Columnas de gestión y notificación en reports
ALTER TABLE reports ADD COLUMN IF NOT EXISTS assigned_to VARCHAR(120);
ALTER TABLE reports ADD COLUMN IF NOT EXISTS assigned_at TIMESTAMPTZ;
ALTER TABLE reports ADD COLUMN IF NOT EXISTS external_delivery_status VARCHAR(32) NOT NULL DEFAULT 'NOT_ENABLED';
ALTER TABLE reports ADD COLUMN IF NOT EXISTS admin_review_status VARCHAR(32) NOT NULL DEFAULT 'PENDING_REVIEW';
ALTER TABLE reports ADD COLUMN IF NOT EXISTS last_public_note TEXT;

-- Tabla de eventos históricos de seguimiento ciudadano
CREATE TABLE IF NOT EXISTS report_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_id UUID NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
    event_type VARCHAR(64) NOT NULL,
    previous_status VARCHAR(32),
    new_status VARCHAR(32),
    public_message TEXT NOT NULL,
    actor_type VARCHAR(32) NOT NULL DEFAULT 'SYSTEM' CHECK (actor_type IN ('CITIZEN', 'SYSTEM', 'ADMIN', 'OPERATOR')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_report_events_report_id ON report_events (report_id, created_at ASC);

-- Tabla de notificaciones internas para administradores de CIVIA
CREATE TABLE IF NOT EXISTS admin_notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_id UUID NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
    title VARCHAR(160) NOT NULL,
    message TEXT NOT NULL,
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    is_synthetic BOOLEAN NOT NULL DEFAULT FALSE,
    read_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_admin_notifications_report UNIQUE (report_id)
);

CREATE INDEX IF NOT EXISTS idx_admin_notifications_unread ON admin_notifications (is_read, created_at DESC);

-- Sembrar eventos iniciales y notificaciones para reportes preexistentes que aún no los tengan
INSERT INTO report_events (id, report_id, event_type, previous_status, new_status, public_message, actor_type, created_at)
SELECT gen_random_uuid(), r.id, 'REPORT_REGISTERED', NULL, r.status, 'Reporte recibido y registrado exitosamente en la plataforma CIVIA.', 'CITIZEN', r.created_at
FROM reports r
WHERE NOT EXISTS (SELECT 1 FROM report_events re WHERE re.report_id = r.id)
ON CONFLICT DO NOTHING;

INSERT INTO admin_notifications (id, report_id, title, message, is_read, is_synthetic, created_at)
SELECT gen_random_uuid(), r.id, 'Nuevo reporte recibido: ' || r.tracking_code, 'Reporte registrado y disponible para revisión administrativa interna.', FALSE, r.is_synthetic, r.created_at
FROM reports r
WHERE NOT EXISTS (SELECT 1 FROM admin_notifications an WHERE an.report_id = r.id)
ON CONFLICT (report_id) DO NOTHING;
