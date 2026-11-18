ALTER TABLE pending_approvals
    ADD COLUMN requested_by uuid REFERENCES users(id) ON DELETE RESTRICT,
    ADD COLUMN expires_at timestamptz NOT NULL DEFAULT (now() + interval '24 hours');

UPDATE pending_approvals SET status = 'REJECTED', decided_at = now(),
    decided_by = 'migration-010', expires_at = now()
WHERE status = 'PENDING' AND requested_by IS NULL;
