from contextlib import asynccontextmanager
import hashlib
import hmac
import json
import logging
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import Depends, FastAPI, File, Form, Header, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from app.agent import decide_pending_approval, list_pending_approvals, run_civia_agent
from app.ai_router import (
    classify_evidence_with_router,
    get_all_circuit_states,
    get_effective_fault_mode,
    get_provider_chain,
    reset_all_circuits,
    set_runtime_fault_override,
    transcribe_audio_optional,
)
from app.config import is_strong_admin_token, settings, validate_admin_token_or_raise
from app.db import check_db_health, run_migrations
from app.observability import get_observability_summary
from app.repository import (
    confirm_report_category,
    create_report,
    get_report_by_tracking_code,
    get_report_raw,
    get_reports_summary_stats,
    list_reports,
    row_to_public_dict,
    update_report_ai_analysis,
    update_report_status,
)
from app.schemas import (
    AgentQueryRequest,
    AgentQueryResponse,
    ApprovalDecisionRequest,
    FaultInjectionRequest,
    ReportConfirmRequest,
    ReportListResponse,
    ReportPublicResponse,
    ReportStatusUpdateRequest,
)
from app.security import (
    CitizenValidationError,
    rate_limiter,
    sanitize_text,
    validate_and_store_audio,
    validate_and_store_photo,
    validate_coordinates,
)
from app.seed import seed_synthetic_reports

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("civia.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_admin_token_or_raise(settings.ADMIN_TOKEN)
    try:
        settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        applied = run_migrations()
        if applied:
            logger.info("Migraciones aplicadas al iniciar: %s", applied)
        if settings.AUTO_SEED_SYNTHETIC:
            seed_res = seed_synthetic_reports(force_reset=False)
            logger.info("Seed sintético inicial: %s", seed_res)
    except Exception as exc:
        logger.warning("Aviso durante inicialización de BD: %s", type(exc).__name__)
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(CitizenValidationError)
async def citizen_validation_exception_handler(request: Request, exc: CitizenValidationError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.code, "message": exc.message},
    )


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "error": "INVALID_PARAMETERS",
            "message": "Los datos enviados en el formulario o consulta no cumplen el formato requerido.",
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error("Fallo interno no controlado en %s: %s", request.url.path, type(exc).__name__)
    return JSONResponse(
        status_code=500,
        content={
            "error": "SERVICE_TEMPORARILY_UNAVAILABLE",
            "message": "No fue posible procesar su solicitud en este momento. Por favor intente nuevamente.",
        },
    )


def verify_admin_token(x_admin_token: str | None = Header(default=None)) -> None:
    expected = (settings.ADMIN_TOKEN or "").strip()
    provided = (x_admin_token or "").strip()
    if (
        not is_strong_admin_token(expected)
        or not is_strong_admin_token(provided)
        or not hmac.compare_digest(provided, expected)
    ):
        raise CitizenValidationError(
            "Acceso restringido a observabilidad y administración.",
            status_code=401,
            code="UNAUTHORIZED",
        )


@app.get("/health")
def health() -> dict[str, Any]:
    db_info = check_db_health()
    return {
        "status": "ok",
        "phase": settings.PHASE,
        "db": db_info,
    }


@app.get("/api/reports/stats")
def reports_stats() -> dict[str, Any]:
    return get_reports_summary_stats()


@app.post("/api/reports", response_model=ReportPublicResponse, status_code=201)
async def create_citizen_report(
    request: Request,
    description: str = Form(...),
    latitude: float = Form(...),
    longitude: float = Form(...),
    title: str | None = Form(default=None),
    comuna: str | None = Form(default=None),
    neighborhood: str | None = Form(default=None),
    address_hint: str | None = Form(default=None),
    auto_analyze: bool = Form(default=True),
    photo: UploadFile = File(...),
    audio: UploadFile | None = File(default=None),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    client_ip = request.client.host if request.client else "unknown"
    rate_limiter.check(client_ip)

    clean_desc = sanitize_text(
        description,
        field_name="descripción",
        min_len=10,
        max_len=2000,
        required=True,
    )
    clean_title = (
        sanitize_text(title, field_name="título", min_len=4, max_len=160, required=False)
        if title and title.strip()
        else (clean_desc[:76] + "..." if len(clean_desc) > 80 else clean_desc)
    )
    clean_comuna = sanitize_text(comuna, field_name="comuna", max_len=64, required=False) or None
    clean_neighborhood = (
        sanitize_text(neighborhood, field_name="barrio", max_len=120, required=False) or None
    )
    clean_address = (
        sanitize_text(address_hint, field_name="dirección o referencia", max_len=255, required=False)
        or None
    )

    lat, lon, in_service_area = validate_coordinates(latitude, longitude)

    raw_photo = await photo.read()
    raw_audio = b""
    if audio is not None and audio.filename:
        raw_audio = await audio.read()

    raw_photo_sha = hashlib.sha256(raw_photo).hexdigest() if raw_photo else ""
    raw_audio_sha = hashlib.sha256(raw_audio).hexdigest() if raw_audio else ""
    canonical_payload = json.dumps(
        {
            "title": clean_title,
            "description": clean_desc,
            "latitude": f"{lat:.6f}",
            "longitude": f"{lon:.6f}",
            "comuna": clean_comuna,
            "neighborhood": clean_neighborhood,
            "address_hint": clean_address,
            "auto_analyze": bool(auto_analyze),
            "photo_sha256": raw_photo_sha,
            "audio_sha256": raw_audio_sha,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    req_fingerprint = hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()

    eff_idem_key: str | None = None
    if idempotency_key is not None and idempotency_key.strip():
        cleaned_idem = idempotency_key.strip()
        if len(cleaned_idem) < 8 or len(cleaned_idem) > 128:
            raise CitizenValidationError(
                "La cabecera Idempotency-Key debe tener entre 8 y 128 caracteres.",
                status_code=422,
                code="INVALID_IDEMPOTENCY_KEY",
            )
        eff_idem_key = cleaned_idem

    written_files: list[Path] = []
    try:
        photo_meta = validate_and_store_photo(raw_photo, declared_filename=photo.filename)
        written_files.append(settings.UPLOAD_DIR / Path(photo_meta["photo_path"]).name)

        audio_meta = None
        audio_transcript = None
        if raw_audio:
            audio_meta = validate_and_store_audio(
                raw_audio, declared_filename=audio.filename if audio else None
            )
            written_files.append(settings.UPLOAD_DIR / Path(audio_meta["audio_path"]).name)
            if auto_analyze:
                try:
                    audio_transcript = transcribe_audio_optional(
                        raw_audio,
                        audio.filename if audio and audio.filename else "audio.wav",
                        audio_meta["audio_mime"],
                    )
                except Exception as exc:
                    logger.warning("Fallo no bloqueante en transcripción opcional: %s", type(exc).__name__)

        create_kwargs: dict[str, Any] = {
            "title": clean_title,
            "description": clean_desc,
            "latitude": lat,
            "longitude": lon,
            "in_service_area": in_service_area,
            "comuna": clean_comuna,
            "neighborhood": clean_neighborhood,
            "address_hint": clean_address,
            "photo_meta": photo_meta,
            "audio_meta": audio_meta,
            "audio_transcript": audio_transcript,
            "idempotency_key": eff_idem_key,
            "request_fingerprint": req_fingerprint,
        }
        row = create_report(**create_kwargs)
    except Exception:
        for orphan_file in written_files:
            orphan_file.unlink(missing_ok=True)
        raise

    if row.get("_replayed"):
        for duplicate_file in written_files:
            duplicate_file.unlink(missing_ok=True)

    saved_edit_token = row.get("_citizen_edit_token")

    if auto_analyze and row.get("status") == "PENDING_ANALYSIS":
        try:
            active_photo_name = Path(row["photo_path"]).name
            safe_photo_file = settings.UPLOAD_DIR / active_photo_name
            stored_photo_bytes = (
                safe_photo_file.read_bytes() if safe_photo_file.exists() else raw_photo
            )
            contract, _ = classify_evidence_with_router(
                description=clean_desc,
                latitude=lat,
                longitude=lon,
                image_bytes=stored_photo_bytes,
                image_mime=row["photo_mime"],
                address_hint=clean_address,
                audio_transcript=row.get("audio_transcript") or audio_transcript,
                report_id=row["id"],
            )
            if contract is not None:
                updated = update_report_ai_analysis(
                    row["id"],
                    ai_category=contract.category,
                    ai_severity=contract.severity,
                    ai_confidence=contract.confidence,
                    ai_summary=contract.summary,
                    ai_keywords=contract.keywords,
                    auto_confirm=False,
                )
                if updated is not None:
                    updated["_citizen_edit_token"] = saved_edit_token
                    row = updated
        except Exception as exc:
            logger.warning(
                "El reporte %s fue confirmado en BD, pero el análisis post-commit falló de forma aislada: %s",
                row.get("tracking_code"),
                type(exc).__name__,
            )

    row["_citizen_edit_token"] = saved_edit_token
    return row_to_public_dict(row)


@app.post("/api/reports/{report_id}/analyze", response_model=ReportPublicResponse)
def analyze_existing_report(request: Request, report_id: UUID):
    client_ip = request.client.host if request.client else "unknown"
    rate_limiter.check(f"analyze:{client_ip}")
    row = get_report_raw(report_id)
    if not row:
        raise CitizenValidationError(
            "No se encontró el reporte solicitado para análisis.",
            status_code=404,
            code="REPORT_NOT_FOUND",
        )
    safe_name = Path(row["photo_path"]).name
    photo_file = settings.UPLOAD_DIR / safe_name
    img_bytes = photo_file.read_bytes() if photo_file.exists() else None

    contract, _ = classify_evidence_with_router(
        description=row["description"],
        latitude=float(row["latitude"]),
        longitude=float(row["longitude"]),
        image_bytes=img_bytes,
        image_mime=row["photo_mime"],
        address_hint=row.get("address_hint"),
        audio_transcript=row.get("audio_transcript"),
        report_id=row["id"],
    )
    if contract is not None:
        updated = update_report_ai_analysis(
            row["id"],
            ai_category=contract.category,
            ai_severity=contract.severity,
            ai_confidence=contract.confidence,
            ai_summary=contract.summary,
            ai_keywords=contract.keywords,
            auto_confirm=False,
        )
        if updated is not None:
            row = updated
    return row_to_public_dict(row)


@app.get("/api/reports", response_model=ReportListResponse)
def list_citizen_reports(
    category: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    status: str | None = Query(default=None),
    comuna: str | None = Query(default=None),
    q: str | None = Query(default=None, max_length=120),
    lat: float | None = Query(default=None, ge=-90.0, le=90.0),
    lon: float | None = Query(default=None, ge=-180.0, le=180.0),
    radius_km: float | None = Query(default=None, gt=0.0, le=100.0),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    total, rows = list_reports(
        category=category,
        severity=severity,
        status=status,
        comuna=comuna,
        q=q,
        lat=lat,
        lon=lon,
        radius_km=radius_km,
        limit=limit,
        offset=offset,
    )
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [row_to_public_dict(r) for r in rows],
    }


@app.get("/api/reports/by-code/{tracking_code}", response_model=ReportPublicResponse)
def get_citizen_report_by_code(tracking_code: str):
    row = get_report_by_tracking_code(tracking_code)
    if not row:
        raise CitizenValidationError(
            "No se encontró ningún reporte con el código indicado.",
            status_code=404,
            code="REPORT_NOT_FOUND",
        )
    return row_to_public_dict(row)


@app.get("/api/reports/{report_id}", response_model=ReportPublicResponse)
def get_citizen_report(report_id: UUID):
    row = get_report_raw(report_id)
    if not row:
        raise CitizenValidationError(
            "No se encontró el reporte solicitado.",
            status_code=404,
            code="REPORT_NOT_FOUND",
        )
    return row_to_public_dict(row)


@app.get("/api/reports/{report_id}/photo")
def get_citizen_report_photo(report_id: UUID):
    row = get_report_raw(report_id)
    if not row:
        raise CitizenValidationError(
            "No se encontró la evidencia fotográfica solicitada.",
            status_code=404,
            code="PHOTO_NOT_FOUND",
        )
    safe_name = Path(row["photo_path"]).name
    file_path = settings.UPLOAD_DIR / safe_name
    if not file_path.exists():
        raise CitizenValidationError(
            "El archivo de imagen no se encuentra disponible en el almacenamiento.",
            status_code=404,
            code="PHOTO_FILE_MISSING",
        )
    return FileResponse(
        path=file_path,
        media_type=row["photo_mime"],
        headers={
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; img-src 'self'; style-src 'none'; script-src 'none'",
            "Cache-Control": "public, max-age=3600",
        },
    )


@app.patch("/api/reports/{report_id}/confirm", response_model=ReportPublicResponse)
def confirm_citizen_report(
    report_id: UUID,
    payload: ReportConfirmRequest,
    x_citizen_edit_token: str | None = Header(default=None),
    x_admin_token: str | None = Header(default=None),
):
    existing = get_report_raw(report_id)
    if not existing:
        raise CitizenValidationError(
            "No se encontró el reporte a confirmar.",
            status_code=404,
            code="REPORT_NOT_FOUND",
        )
    clean_note = (
        sanitize_text(
            payload.human_override_note,
            field_name="nota de confirmación",
            max_len=500,
            required=False,
        )
        or None
    )
    expected_admin = (settings.ADMIN_TOKEN or "").strip()
    provided_admin = (x_admin_token or "").strip()
    is_admin = (
        is_strong_admin_token(expected_admin)
        and is_strong_admin_token(provided_admin)
        and hmac.compare_digest(provided_admin, expected_admin)
    )
    eff_edit_token = x_citizen_edit_token or payload.edit_token
    updated = confirm_report_category(
        report_id,
        final_category=payload.final_category,
        final_severity=payload.final_severity,
        human_override_note=clean_note,
        edit_token=eff_edit_token,
        is_admin=is_admin,
    )
    assert updated is not None
    return row_to_public_dict(updated)


@app.patch(
    "/api/reports/{report_id}/status",
    response_model=ReportPublicResponse,
    dependencies=[Depends(verify_admin_token)],
)
def change_report_status(report_id: UUID, payload: ReportStatusUpdateRequest):
    if not payload.human_approved:
        raise CitizenValidationError(
            "Se requiere confirmación humana explícita para modificar el estado del reporte.",
            status_code=400,
            code="HUMAN_APPROVAL_REQUIRED",
        )
    existing = get_report_raw(report_id)
    if not existing:
        raise CitizenValidationError(
            "No se encontró el reporte solicitado.",
            status_code=404,
            code="REPORT_NOT_FOUND",
        )
    clean_note = (
        sanitize_text(payload.note, field_name="nota de estado", max_len=500, required=False) or None
    )
    updated = update_report_status(report_id, status=payload.status, note=clean_note)
    assert updated is not None
    return row_to_public_dict(updated)


@app.post("/api/agent/query", response_model=AgentQueryResponse)
def query_civia_agent(request: Request, payload: AgentQueryRequest):
    client_ip = request.client.host if request.client else "unknown"
    rate_limiter.check(f"agent:{client_ip}")
    clean_q = sanitize_text(
        payload.query,
        field_name="consulta",
        min_len=3,
        max_len=1000,
        required=True,
    )
    res = run_civia_agent(
        clean_q,
        max_iterations=payload.max_iterations,
        max_tokens_budget=payload.max_tokens_budget,
        tool_timeout_seconds=payload.tool_timeout_seconds or 4.0,
        total_timeout_seconds=payload.total_timeout_seconds,
    )
    return {
        "answer": res["answer"],
        "trace_group_id": res["trace_group_id"],
        "tools_invoked": res["tools_invoked"],
        "iterations_used": res["iterations_used"],
        "max_iterations": res["max_iterations"],
        "total_tokens_used": res["total_tokens_used"],
        "max_tokens_budget": res["max_tokens_budget"],
        "latency_ms": res["latency_ms"],
        "guardrail_triggered": res.get("guardrail_triggered"),
        "requires_human_approval": res.get("requires_human_approval", False),
        "pending_approval_id": res.get("pending_approval_id"),
    }


@app.get("/api/admin/observability", dependencies=[Depends(verify_admin_token)])
def admin_get_observability(limit: int = Query(default=60, ge=1, le=300)) -> dict[str, Any]:
    summary = get_observability_summary(limit=limit)
    chain_public = [
        {"tier": c["tier"], "provider": c["provider"], "model": c["model"], "configured": bool(c["api_key"])}
        for c in get_provider_chain()
    ]
    return {
        "provider_chain": chain_public,
        "circuit_breakers": get_all_circuit_states(),
        "effective_fault_mode": get_effective_fault_mode() or "NONE",
        "observability": summary,
    }


@app.post("/api/admin/fault-injection", dependencies=[Depends(verify_admin_token)])
def admin_set_fault_injection(payload: FaultInjectionRequest) -> dict[str, Any]:
    active = set_runtime_fault_override(payload.mode)
    if payload.reset_circuits:
        reset_all_circuits()
    return {
        "effective_fault_mode": get_effective_fault_mode() or "NONE",
        "runtime_override": active or "NONE",
        "circuit_breakers": get_all_circuit_states(),
    }


@app.get("/api/admin/approvals", dependencies=[Depends(verify_admin_token)])
def admin_list_approvals(status: str | None = Query(default=None)) -> dict[str, Any]:
    items = list_pending_approvals(status=status)
    return {"total": len(items), "items": items}


@app.post("/api/admin/approvals/{approval_id}/decide", dependencies=[Depends(verify_admin_token)])
def admin_decide_approval(approval_id: UUID, payload: ApprovalDecisionRequest) -> dict[str, Any]:
    updated = decide_pending_approval(
        approval_id,
        approve=payload.approve,
        decided_by=payload.decided_by,
    )
    if not updated:
        raise CitizenValidationError(
            "No se encontró la solicitud de aprobación indicada.",
            status_code=404,
            code="APPROVAL_NOT_FOUND",
        )
    if payload.approve and updated.get("stale_conflict"):
        raise CitizenValidationError(
            "La solicitud de aprobación quedó obsoleta porque el estado o versión del reporte cambió previamente.",
            status_code=409,
            code="STALE_APPROVAL",
        )
    return {"status": "ok", "approval": updated}


@app.post("/api/admin/seed", dependencies=[Depends(verify_admin_token)])
def admin_seed_reports(force_reset: bool = Query(default=False)) -> dict[str, Any]:
    return seed_synthetic_reports(force_reset=force_reset)
