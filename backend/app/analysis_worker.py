"""Proceso independiente que ejecuta diagnósticos para la cola durable."""

from hashlib import sha256
import logging
import os
from pathlib import Path
import signal
import socket
import sys
from threading import Event
from uuid import uuid4

import psycopg
from psycopg.conninfo import conninfo_to_dict

from app.ai_router import AIProviderError, classify_evidence_with_router, get_all_circuit_states, transcribe_audio_optional
from app.analysis_queue import claim_job, fail_job, finish_job, get_job_evidence, worker_available
from app.config import settings
from app.schemas import AIAnalysisContract
from app.security import sanitize_generated_text

logger = logging.getLogger("civia.analysis_worker")


def _read_evidence(filename: str, size: int, digest: str, limit: int) -> bytes:
    root = settings.UPLOAD_DIR.resolve()
    path = root / Path(filename).name
    if path.is_symlink():
        raise OSError("Evidencia no disponible")
    with path.open("rb") as source:
        data = source.read(limit + 1)
    if (
        len(data) != size or len(data) > limit or sha256(data).hexdigest() != digest
    ):
        raise OSError("Evidencia no disponible")
    return data


def process_next_job(worker_id: str) -> bool:
    timeout_seconds = min(120.0, max(1.0, settings.AI_TIMEOUT_SECONDS))
    job = claim_job(
        worker_id, lease_seconds=int(timeout_seconds) + 36,
        circuit_breakers=get_all_circuit_states(),
    )
    if job is None:
        return False
    evidence = get_job_evidence(job)
    if evidence is None:
        # Ante una decisión humana o una versión obsoleta, la cola cancela el trabajo.
        fail_job(job, "INPUT_INVALID", retryable=False)
        return True
    try:
        photo = _read_evidence(
            evidence["photo_path"], evidence["photo_size_bytes"], evidence["photo_sha256"],
            settings.MAX_PHOTO_BYTES,
        )
    except OSError:
        fail_job(job, "MISSING_EVIDENCE", retryable=False)
        return True
    try:
        transcript = None
        if evidence["audio_path"] and evidence["audio_sha256"]:
            try:
                audio = _read_evidence(
                    evidence["audio_path"], evidence["audio_size_bytes"], evidence["audio_sha256"],
                    settings.MAX_AUDIO_BYTES,
                )
                filename = "audio" + Path(evidence["audio_path"]).suffix
                transcript = sanitize_generated_text(
                    transcribe_audio_optional(audio, filename, evidence["audio_mime"]), 600,
                )
            except OSError:
                logger.warning("La nota opcional del trabajo %s no está disponible.", job.id)

        analysis, _ = classify_evidence_with_router(
            description=evidence["description"],
            latitude=round(evidence["latitude"], 2),
            longitude=round(evidence["longitude"], 2),
            image_bytes=photo,
            image_mime=evidence["photo_mime"],
            audio_transcript=transcript,
            report_id=job.report_id,
            total_timeout_override=timeout_seconds,
            for_queue=True,
        )
        if not isinstance(analysis, AIAnalysisContract):
            fail_job(job, "INVALID_SCHEMA", retryable=True)
        else:
            # Revalida el modelo de salida en la frontera de persistencia, incluso
            # si el adaptador entregó una instancia construida sin validación.
            finish_job(job, AIAnalysisContract.model_validate(analysis.model_dump()), transcript=transcript)
    except AIProviderError as exc:
        code = {
            "MISSING_API_KEY": "CONFIGURATION",
            "MODALITY_UNSUPPORTED": "CONFIGURATION",
            "MODEL_UNAVAILABLE": "CONFIGURATION",
            "HTTP_401": "CONFIGURATION",
            "HTTP_403": "CONFIGURATION",
            "HTTP_404": "CONFIGURATION",
        }.get(exc.code, exc.code)
        fail_job(
            job, code, retryable=exc.retryable, retry_after_seconds=exc.retry_after_seconds,
            defer_attempt=exc.defer_attempt,
        )
    except psycopg.Error:
        # La transacción fallida deja intacto el arrendamiento y su recuperación.
        raise
    except Exception as exc:
        logger.warning("Fallo inesperado en trabajo %s (%s).", job.id, type(exc).__name__)
        fail_job(job, "INTERNAL_ERROR", retryable=True)
    return True


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    worker_dsn = os.getenv("WORKER_DATABASE_URL")
    if not worker_dsn:
        logger.error("Falta la conexión PostgreSQL del worker.")
        return 1
    try:
        if conninfo_to_dict(worker_dsn).get("user") != "civia_worker":
            logger.error("La conexión PostgreSQL del worker requiere su rol dedicado.")
            return 1
    except psycopg.Error:
        logger.error("La conexión PostgreSQL del worker no tiene un formato válido.")
        return 1
    settings.DATABASE_URL = worker_dsn
    if sys.argv[1:] == ["--healthcheck"]:
        try:
            return 0 if worker_available() else 1
        except psycopg.Error:
            return 1

    stop = Event()

    def request_stop(*_):
        stop.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    worker_id = f"{socket.gethostname()[:64]}:{uuid4()}"
    idle_seconds = min(10.0, max(0.25, float(os.getenv("QUEUE_POLL_SECONDS", "2"))))
    while not stop.is_set():
        try:
            if not process_next_job(worker_id):
                stop.wait(idle_seconds)
        except psycopg.Error as exc:
            logger.warning("Cola temporalmente indisponible (%s).", type(exc).__name__)
            stop.wait(max(5.0, idle_seconds))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
