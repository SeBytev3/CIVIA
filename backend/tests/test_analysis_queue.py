from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from hashlib import sha256
from uuid import uuid4

import pytest
import psycopg

from app.config import settings
from app.db import ensure_isolated_database, get_agent_conn, get_conn, run_migrations
from app.repository import confirm_report_category, create_report, get_report_raw, list_reports, row_to_public_dict
from app.schemas import AIAnalysisContract
from app.security import CitizenValidationError


@pytest.fixture(scope="module")
def queue_db_url():
    dsn = ensure_isolated_database(f"civia_test_queue_{uuid4().hex[:8]}", settings.DATABASE_URL)
    run_migrations(database_url=dsn)
    return dsn


@pytest.fixture(autouse=True)
def isolated_queue(monkeypatch, queue_db_url):
    monkeypatch.setattr(settings, "DATABASE_URL", queue_db_url)
    # La base existe únicamente para este módulo y contiene datos sintéticos.
    with get_conn() as conn:
        conn.execute("DELETE FROM analysis_jobs")
        conn.commit()


def _create_report(*, key=None, evidence=None, audio=None, owner_id=None):
    return create_report(
        title="Reporte sintético de cola",
        description="Descripción sintética para la verificación hermética de la cola.",
        latitude=3.44,
        longitude=-76.53,
        in_service_area=True,
        comuna=None,
        neighborhood=None,
        address_hint=None,
        idempotency_key=key,
        audio_meta=audio,
        owner_id=owner_id,
        photo_meta=evidence or {
            "photo_path": "synthetic.jpg",
            "photo_mime": "image/jpeg",
            "photo_size_bytes": 1024,
            "photo_width": 64,
            "photo_height": 64,
            "photo_sha256": "a" * 64,
        },
    )


def _analysis():
    return AIAnalysisContract(
        category="HUECO", severity="MEDIA", confidence=0.9,
        summary="La evidencia sintética muestra un hueco.", keywords=["vía"],
    )


def _user(role="CITIZEN"):
    user_id = uuid4()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO users (id, name, email, password_hash, role)
            VALUES (%s, 'Cuenta sintética', %s, '$argon2id$fixture', %s)
            """,
            (user_id, f"{user_id}@example.test", role),
        )
        conn.commit()
    return user_id


def test_receipt_replay_creates_only_one_job():
    key = str(uuid4())
    report = _create_report(key=key)
    assert _create_report(key=key)["id"] == report["id"]
    with get_conn() as conn:
        jobs = conn.execute("SELECT state FROM analysis_jobs WHERE report_id = %s", (report["id"],)).fetchall()
    assert jobs == [{"state": "QUEUED"}]


def test_queue_failure_rolls_back_receipt(monkeypatch):
    from app import repository

    def unavailable(*args, **kwargs):
        raise RuntimeError("synthetic queue failure")

    monkeypatch.setattr(repository, "enqueue_in_transaction", unavailable)
    with get_conn() as conn:
        before = conn.execute("SELECT count(*) AS count FROM reports").fetchone()
    with pytest.raises(RuntimeError, match="synthetic queue failure"):
        _create_report()
    with get_conn() as conn:
        assert conn.execute("SELECT count(*) AS count FROM reports").fetchone() == before


def test_lost_commit_acknowledgement_leaves_receipt_safe_to_replay(monkeypatch):
    from app import repository

    @contextmanager
    def lose_acknowledgement(*args, **kwargs):
        with get_conn(*args, **kwargs) as conn:
            actual_commit = conn.commit

            def commit():
                actual_commit()
                raise psycopg.OperationalError("synthetic lost acknowledgement")

            conn.commit = commit
            yield conn

    key = str(uuid4())
    with monkeypatch.context() as scoped:
        scoped.setattr(repository, "get_conn", lose_acknowledgement)
        with pytest.raises(repository.ReceiptCommitUncertain):
            _create_report(key=key)
    replay = _create_report(key=key)
    assert replay["_replayed"] is True
    with get_conn() as conn:
        report_jobs = conn.execute("SELECT id FROM analysis_jobs WHERE report_id = %s", (replay["id"],)).fetchall()
    assert len(report_jobs) == 1


def test_concurrent_claims_cannot_share_a_job_and_human_decision_wins():
    from app.analysis_queue import claim_job, finish_job

    report = _create_report()
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = list(pool.map(claim_job, ("first", "second")))
    jobs = [job for job in jobs if job and job.report_id == report["id"]]
    assert len(jobs) == 1
    confirm_report_category(report["id"], final_category="BASURAS", is_admin=True)
    assert finish_job(jobs[0], _analysis()) is False
    row = get_report_raw(report["id"])
    assert row["final_category"] == "BASURAS"
    assert row["ai_category"] is None


def test_expired_fence_cannot_publish_even_without_replacement():
    from app.analysis_queue import claim_job, finish_job

    report = _create_report()
    job = claim_job("first")
    assert job and job.report_id == report["id"]
    with get_conn() as conn:
        conn.execute(
            "UPDATE analysis_jobs SET lease_expires_at = clock_timestamp() - interval '1 second' WHERE id = %s",
            (job.id,),
        )
        conn.commit()
    assert finish_job(job, _analysis()) is False
    assert get_report_raw(report["id"])["ai_category"] is None


def test_terminal_failure_keeps_report_and_requeues_idempotently():
    from app.analysis_queue import claim_job, fail_job, list_dead_letters, requeue_dead_letter

    report = _create_report()
    job = claim_job("first")
    assert job and job.report_id == report["id"]
    assert fail_job(job, "CONFIGURATION", retryable=False)
    assert row_to_public_dict(get_report_raw(report["id"]))["analysis_status"] == "MANUAL_REVIEW"
    assert any(entry["id"] == job.id for entry in list_dead_letters())
    actor = _user("WEB_ADMIN")
    assert requeue_dead_letter(job.id, actor)
    assert requeue_dead_letter(job.id, actor)
    assert row_to_public_dict(get_report_raw(report["id"]))["analysis_status"] == "PENDING"
    requeued = claim_job("replacement")
    assert fail_job(requeued, "CONFIGURATION", retryable=False)
    assert requeue_dead_letter(job.id, actor)
    assert row_to_public_dict(get_report_raw(report["id"]))["analysis_status"] == "MANUAL_REVIEW"
    assert not requeue_dead_letter(job.id, _user("CASE_ADMIN"), "test-requeue-02")
    assert requeue_dead_letter(job.id, actor, "test-requeue-02")
    with get_conn() as conn:
        assert conn.execute(
            "SELECT count(*) AS total FROM security_audit WHERE action = 'queue.requeue' AND target_id = %s",
            (job.id,),
        ).fetchone()["total"] == 2


def test_agent_connection_is_read_only_and_has_only_minimal_view():
    with get_agent_conn() as conn:
        profile = conn.execute(
            """
            SELECT current_user AS role, current_setting('transaction_read_only') AS read_only,
                has_table_privilege(current_user, 'agent_reports', 'SELECT') AS view_access,
                has_table_privilege(current_user, 'reports', 'SELECT') AS report_access,
                has_table_privilege(current_user, 'auth_sessions', 'SELECT') AS session_access,
                has_table_privilege(current_user, 'report_internal_notes', 'SELECT') AS notes_access,
                has_table_privilege(current_user, 'agent_reports', 'UPDATE') AS can_update
            """
        ).fetchone()
        visible = conn.execute("SELECT id FROM agent_reports").fetchall()
    assert profile == {
        "role": "civia_agent", "read_only": "on", "view_access": True,
        "report_access": False, "session_access": False, "notes_access": False,
        "can_update": False,
    }
    assert visible == []


def test_worker_validates_voice_and_stores_sanitized_transcript(monkeypatch):
    from app import analysis_worker

    photo, audio = b"synthetic image", b"synthetic voice"
    photo_path = settings.UPLOAD_DIR / f"{uuid4().hex}.jpg"
    audio_path = settings.UPLOAD_DIR / f"{uuid4().hex}.wav"
    photo_path.write_bytes(photo)
    audio_path.write_bytes(audio)
    report = _create_report(
        evidence={
            "photo_path": photo_path.name, "photo_mime": "image/jpeg",
            "photo_size_bytes": len(photo), "photo_sha256": sha256(photo).hexdigest(),
            "photo_width": 64, "photo_height": 64,
        },
        audio={
            "audio_path": audio_path.name, "audio_mime": "audio/wav", "audio_size_bytes": len(audio),
            "audio_duration_seconds": 1.0, "audio_sha256": sha256(audio).hexdigest(),
        },
    )
    monkeypatch.setattr(
        analysis_worker, "transcribe_audio_optional",
        lambda data, *_: "Daño en la vía. Contacto cuenta@example.test." if data == audio else None,
    )

    def classify(**kwargs):
        assert kwargs["image_bytes"] == photo
        assert kwargs["audio_transcript"] == "Daño en la vía. Contacto [CORREO_PROTEGIDO]."
        analysis = _analysis().model_copy(update={"summary": "Daño en la vía. Ver https://example.test/path"})
        return analysis, {}

    monkeypatch.setattr(analysis_worker, "classify_evidence_with_router", classify)
    assert analysis_worker.process_next_job("voice-worker")
    row = get_report_raw(report["id"])
    assert row["ai_category"] == "HUECO"
    assert "CORREO_PROTEGIDO" in row["audio_transcript"]
    assert "example.test" not in row["ai_summary"]


def test_retry_continues_after_abandoned_lease_then_moves_to_manual_review(monkeypatch):
    from app import analysis_queue as queue

    monkeypatch.setattr(queue, "MAX_ATTEMPTS", 2)
    report = _create_report()
    first = queue.claim_job("first")

    def expire(job):
        with get_conn() as conn:
            conn.execute(
                "UPDATE analysis_jobs SET lease_expires_at = clock_timestamp() - interval '1 second' WHERE id = %s",
                (job.id,),
            )
            conn.commit()

    expire(first)
    assert queue.fail_job(first, "TIMEOUT", retryable=True) is False
    assert queue.claim_job("replacement") is None
    pending = row_to_public_dict(get_report_raw(report["id"]))
    assert pending["analysis_delayed"] is True
    assert "No necesitas enviarlo nuevamente" in pending["analysis_status_message"]
    with get_conn() as conn:
        conn.execute(
            "UPDATE analysis_jobs SET available_at = clock_timestamp() - interval '1 second' WHERE id = %s",
            (first.id,),
        )
        conn.commit()
    replacement = queue.claim_job("replacement")
    assert replacement.id == first.id and replacement.fence > first.fence
    assert queue.finish_job(first, _analysis()) is False
    expire(replacement)
    assert queue.claim_job("third") is None
    assert queue.list_dead_letters()[0]["last_error"] == "LEASE_EXPIRED"
    assert row_to_public_dict(get_report_raw(report["id"]))["analysis_status"] == "MANUAL_REVIEW"


def test_owner_admission_and_replay_remain_scoped(monkeypatch):
    from app import analysis_queue as queue

    monkeypatch.setattr(queue, "MAX_PENDING_PER_OWNER", 1)
    first_owner, other_owner = _user(), _user()
    key = str(uuid4())
    first = _create_report(key=key, owner_id=first_owner)
    other = _create_report(key=key, owner_id=other_owner)
    assert first["id"] != other["id"]
    assert _create_report(key=key, owner_id=first_owner)["id"] == first["id"]
    with pytest.raises(CitizenValidationError) as error:
        _create_report(owner_id=first_owner)
    assert error.value.status_code == 429
    total, own_reports = list_reports(owner_id=first_owner)
    assert total == 1 and own_reports[0]["id"] == first["id"]
    assert get_report_raw(other["id"], owner_id=first_owner) is None
    with get_agent_conn(first_owner) as conn:
        assert conn.execute("SELECT id FROM agent_reports").fetchall() == [{"id": first["id"]}]


def test_budget_delay_does_not_consume_attempt():
    from app import analysis_queue as queue

    report = _create_report()
    job = queue.claim_job("first")
    assert queue.fail_job(
        job, "BUDGET_EXHAUSTED", retryable=True, retry_after_seconds=60, defer_attempt=True,
    )
    with get_conn() as conn:
        result = conn.execute(
            """
            SELECT attempts, extract(epoch FROM available_at - clock_timestamp()) AS seconds
            FROM analysis_jobs WHERE id = %s
            """,
            (job.id,),
        ).fetchone()
    assert result["attempts"] == 0
    assert 50 <= result["seconds"] <= 60
    assert row_to_public_dict(get_report_raw(report["id"]))["analysis_delayed"] is True
