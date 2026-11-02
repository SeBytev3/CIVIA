-- 003_invalidate_legacy_approvals.sql
-- Bloque G1.1 (A-07): Invalidar propuestas PENDING heredadas que carezcan de expected_version o previous_status
-- sin inventar versiones retroactivas.

UPDATE pending_approvals
SET status = 'REJECTED',
    decided_by = COALESCE(decided_by, 'system-migration-003'),
    decided_at = COALESCE(decided_at, NOW()),
    reason = LEFT(
        COALESCE(reason, '') || ' [Invalidada en migración 003: propuesta heredada sin expected_version]',
        500
    )
WHERE status = 'PENDING'
  AND (
      NOT (proposed_payload ? 'expected_version')
      OR NOT (proposed_payload ? 'previous_status')
      OR jsonb_typeof(proposed_payload->'expected_version') != 'number'
  );
