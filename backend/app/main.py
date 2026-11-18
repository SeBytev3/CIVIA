from contextlib import asynccontextmanager
import hashlib
import json
import logging
import os
from pathlib import Path
import re
from typing import Any, Literal
from uuid import UUID

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.agent import (
    OperationPendingError,
    decide_pending_approval,
    list_pending_approvals,
    run_civia_agent,
)
from app.ai_router import (
    get_all_circuit_states,
    get_effective_fault_mode,
    get_provider_chain,
    reset_all_circuits,
    set_runtime_fault_override,
)
from app.analysis_queue import enqueue_report_analysis, list_dead_letters, queue_status, requeue_dead_letter
from app.auth_routes import ALLOWED_ORIGINS, auth_router, users_router
from app.config import settings
from app.db import (
    IdempotencyConflictError,
    check_db_health,
    get_conn,
    get_operation_record,
    reconcile_operation,
    run_migrations,
    sanitize_credentials_deep,
)
from app.identity import (
    CaseAdminSession,
    CitizenSession,
    CurrentSession,
    Role,
    WebAdminSession,
    audit,
    require_case_admin,
    require_web_admin,
)
from app.observability import get_observability_summary
from app.public_map import router as public_map_router
from app.repository import (
    ReceiptCommitUncertain,
    confirm_report_category,
    create_report,
    get_report_by_tracking_code,
    get_report_raw,
    get_reports_summary_stats,
    list_admin_notifications,
    list_reports,
    mark_admin_notification_read,
    mark_all_admin_notifications_read,
    row_to_public_dict,
    update_report_management,
    update_report_status,
)
from app.seed import get_known_synthetic_sha256_set
from app.schemas import (
    AdminNotificationsResponse,
    AgentQueryRequest,
    AgentQueryResponse,
    ApprovalDecisionRequest,
    FaultInjectionRequest,
    OperationStatusResponse,
    ReportConfirmRequest,
    ReportEventPublic,
    ReportListResponse,
    ReportManagementUpdateRequest,
    ReportPublicResponse,
    ReportStatusUpdateRequest,
)
from app.security import (
    CitizenValidationError,
    get_trusted_client_ip,
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
    try:
        settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        if os.getenv("CIVIA_EXTERNAL_MIGRATIONS") != "1":
            applied = run_migrations()
            if applied:
                logger.info("Migraciones aplicadas al iniciar: %s", applied)
        if settings.AUTO_SEED_SYNTHETIC:
            seed_res = seed_synthetic_reports(force_reset=False)
            logger.info("Seed sintético inicial: %s", seed_res)
    except Exception as exc:
        logger.warning("Aviso durante inicialización de BD: %s", type(exc).__name__)
    yield


TAGS_METADATA = [
    {
        "name": "Salud del sistema",
        "description": "Verificación del estado operativo de la API REST, fase del sistema y conectividad transaccional con la base de datos PostgreSQL 17.",
    },
    {
        "name": "Reportes ciudadanos",
        "description": "Registro y consulta por propietario, con acceso operativo para los perfiles administrativos.",
    },
    {
        "name": "Fotografías y evidencias",
        "description": "Entrega autenticada de evidencias fotográficas y notas de voz con controles de propiedad y caché privada.",
    },
    {
        "name": "Seguimiento y trazabilidad",
        "description": "Línea de tiempo cronológica y pública de eventos operativos (`report_events`) generados durante el ciclo de vida del reporte.",
    },
    {
        "name": "Asistente ciudadano e IA",
        "description": "Interacción conversacional con el agente inteligente de CIVIA mediante SQL directo tipado, 4 límites efectivos y recuperación de operaciones.",
    },
    {
        "name": "Administración y gestión operativa",
        "description": "Consola administrativa protegida: bandeja de notificaciones internas, asignación de dependencias y actualización controlada de estados.",
    },
    {
        "name": "Aprobaciones humanas",
        "description": "Guardrail ético #4: gestión y decisión humana sobre solicitudes de escritura crítica propuestas por la IA en la tabla `pending_approvals`.",
    },
    {
        "name": "Observabilidad y resiliencia",
        "description": "Monitoreo técnico de latencias P50/P90, estado de circuit breakers de proveedores multimodales, trazas sanitizadas y simulación de fallas.",
    },
]

APP_DESCRIPTION = """
**CIVIA (Ciudad Inteligente y Vigilancia Ambiental)** es la plataforma oficial para la captura, diagnóstico asistido por IA, confirmación ciudadana y seguimiento operativo de incidentes urbanos y ambientales en **Santiago de Cali y el Valle del Cauca** (*Huecos, Basuras, Tala arbórea y Quemas*).

### Arquitectura y Principios de Diseño:
* **API RESTful de Alto Rendimiento:** Construida con FastAPI en Python 3.13 con validación de esquemas mediante Pydantic v2.
* **Persistencia Transaccional:** Motor PostgreSQL 17 con esquema relacional normalizado e integridad referencial estricta.
* **Análisis resiliente:** Un worker consume una cola persistente con dos proveedores, interruptores de circuito y reintentos acotados.
* **Agente Genuino con SQL Directo y Cuatro Límites:** Invocación de herramientas tipadas parametrizadas sin intermediarios opacos; la IA jamás escribe directamente en la base de datos de reportes.
* **Seguridad y privacidad:** Evidencias privadas, credenciales Argon2id, sesiones revocables, permisos por rol y propiedad.

Para la especificación exhaustiva de cada endpoint, guías de desarrollo y códigos de respuesta, consulte la documentación canónica en [`docs/API.md`](https://github.com/SeBytev3/CIVIA/blob/main/docs/API.md).
"""

app = FastAPI(
    title="CIVIA — API de Gestión Inteligente y Vigilancia Urbana",
    description=APP_DESCRIPTION,
    version=settings.VERSION,
    openapi_tags=TAGS_METADATA,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(ALLOWED_ORIGINS),
    allow_credentials=True,
    allow_methods=["GET", "HEAD", "POST", "PATCH", "OPTIONS"],
    allow_headers=[
        "Authorization", "Content-Type", "Idempotency-Key", "X-CSRF-Token",
        "X-Operation-Token", "X-Session-Mode", "X-Civia-Account", "X-Civia-Installation",
    ],
)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(public_map_router)


@app.middleware("http")
async def prevent_api_caching(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


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


@app.get(
    "/health",
    tags=["Salud del sistema"],
    summary="Comprobar salud y conectividad de la plataforma",
    description="Verifica la disponibilidad de la API REST, la versión y fase activa, y el estado de la conexión a la base de datos PostgreSQL 17 junto con la preparación del esquema.",
    responses={503: {"description": "La base de datos o el esquema no está disponible"}},
)
def health(response: Response) -> dict[str, Any]:
    payload = _health_payload()
    if payload["status"] != "ok":
        response.status_code = 503
    response.headers["Cache-Control"] = "no-store"
    return payload


def _health_payload() -> dict[str, Any]:
    db_info = check_db_health()
    return {
        "status": "ok" if db_info["connected"] and db_info["schema_ready"] else "degraded",
        "version": settings.VERSION,
        "phase": settings.PHASE,
        "db": db_info,
    }


class InstallationMetadata(BaseModel):
    version: str
    commit: str
    installation_id: UUID
    protocol: Literal[1] = 1


def _installation_id() -> UUID:
    with get_conn(2000) as conn:
        row = conn.execute("SELECT installation_id FROM installation_metadata WHERE singleton").fetchone()
    if row is None:
        raise HTTPException(status_code=503, detail="Identidad de instalación no disponible.")
    return row["installation_id"]


@app.get("/api/meta", tags=["Salud del sistema"], response_model=InstallationMetadata,
         summary="Identificar la instalación y la compilación de CIVIA")
def installation_metadata() -> InstallationMetadata:
    sha = settings.BUILD_SHA
    return InstallationMetadata(
        version=settings.VERSION,
        commit=sha if re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})(?:-dirty)?", sha) else "unknown",
        installation_id=_installation_id(),
    )


@app.get(
    "/api/reports/stats",
    tags=["Reportes ciudadanos"],
    summary="Obtener estadísticas generales de reportes",
    description="Devuelve estadísticas de los reportes propios o de toda la operación según el rol.",
)
def reports_stats(principal: CurrentSession) -> dict[str, Any]:
    return get_reports_summary_stats(owner_id=_citizen_owner(principal))


def _citizen_owner(principal: CurrentSession) -> UUID | None:
    return principal.id if principal.role == Role.CITIZEN else None


def _visible_report(row: dict[str, Any] | None) -> dict[str, Any]:
    if row is None:
        raise CitizenValidationError(
            "No se encontró el reporte solicitado.", status_code=404, code="REPORT_NOT_FOUND"
        )
    return row


@app.post(
    "/api/reports",
    response_model=ReportPublicResponse,
    status_code=201,
    tags=["Reportes ciudadanos"],
    summary="Crear nuevo reporte ciudadano con evidencia fotográfica",
    description="Guarda el reporte del usuario autenticado, elimina los metadatos fotográficos y encola el diagnóstico.",
)
async def create_citizen_report(
    request: Request,
    principal: CitizenSession,
    description: str = Form(...),
    latitude: float = Form(...),
    longitude: float = Form(...),
    title: str | None = Form(default=None),
    comuna: str | None = Form(default=None),
    neighborhood: str | None = Form(default=None),
    address_hint: str | None = Form(default=None),
    photo: UploadFile = File(...),
    audio: UploadFile | None = File(default=None),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    expected_account: UUID | None = Header(default=None, alias="X-Civia-Account"),
    expected_installation: UUID | None = Header(default=None, alias="X-Civia-Installation"),
):
    if expected_account is not None or expected_installation is not None:
        if (expected_account != principal.id or expected_installation is None
                or expected_installation != await run_in_threadpool(_installation_id)):
            raise CitizenValidationError(
                "La cuenta o el servidor cambió. El borrador sigue guardado en el dispositivo.",
                status_code=409,
                code="REPORT_SCOPE_CHANGED",
            )

    client_ip = get_trusted_client_ip(request)
    rate_limiter.check(f"report:ip:{client_ip}")
    rate_limiter.check(f"report:user:{principal.id}")

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

    raw_photo = await photo.read(settings.MAX_PHOTO_BYTES + 1)
    raw_audio = b""
    if audio is not None and audio.filename:
        raw_audio = await audio.read(settings.MAX_AUDIO_BYTES + 1)

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
        photo_meta = await run_in_threadpool(validate_and_store_photo, raw_photo, declared_filename=photo.filename)
        written_files.append(settings.UPLOAD_DIR / Path(photo_meta["photo_path"]).name)

        audio_meta = None
        if raw_audio:
            audio_meta = await run_in_threadpool(
                validate_and_store_audio, raw_audio, declared_filename=audio.filename if audio else None
            )
            written_files.append(settings.UPLOAD_DIR / Path(audio_meta["audio_path"]).name)

        known_synthetic = get_known_synthetic_sha256_set()
        # Procedencia certificada por servidor: la condición sintética oficial de prueba
        # se determina estrictamente por la coincidencia criptográfica del contenido con
        # los activos validados del catálogo CIVIA, impidiendo falsificaciones del cliente.
        eff_is_synthetic = bool(
            (raw_photo_sha in known_synthetic)
            or (photo_meta["photo_sha256"] in known_synthetic)
        )

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
            "is_synthetic": eff_is_synthetic,
            "idempotency_key": eff_idem_key,
            "request_fingerprint": req_fingerprint,
            "owner_id": principal.id,
            "enqueue_analysis": True,
        }
        row = await run_in_threadpool(create_report, **create_kwargs)
    except ReceiptCommitUncertain as exc:
        raise CitizenValidationError(
            "No pudimos confirmar la recepción. Reintenta este mismo envío sin crear otro reporte.",
            status_code=503,
            code="RECEIPT_UNCONFIRMED",
        ) from exc
    except Exception:
        for orphan_file in written_files:
            orphan_file.unlink(missing_ok=True)
        raise

    if row.get("_replayed"):
        for duplicate_file in written_files:
            duplicate_file.unlink(missing_ok=True)

    row.pop("_citizen_edit_token", None)
    return row_to_public_dict(row)


@app.post(
    "/api/reports/{report_id}/analyze",
    response_model=ReportPublicResponse,
    status_code=202,
    tags=["Reportes ciudadanos"],
    summary="Ejecutar análisis multimodal sobre reporte existente",
    description="Encola el diagnóstico de un reporte propio pendiente de análisis.",
)
def analyze_existing_report(request: Request, report_id: UUID, principal: CitizenSession):
    client_ip = get_trusted_client_ip(request)
    rate_limiter.check(f"analyze:ip:{client_ip}")
    rate_limiter.check(f"analyze:user:{principal.id}")
    _visible_report(get_report_raw(report_id, include_events=False, owner_id=principal.id))
    if not enqueue_report_analysis(report_id, owner_id=principal.id):
        raise CitizenValidationError(
            "El reporte no está disponible para un nuevo análisis.",
            status_code=409,
            code="ANALYSIS_NOT_AVAILABLE",
        )
    return row_to_public_dict(_visible_report(get_report_raw(report_id, owner_id=principal.id)))


@app.get(
    "/api/reports",
    response_model=ReportListResponse,
    tags=["Reportes ciudadanos"],
    summary="Listar reportes ciudadanos con filtros",
    description="Consulta paginada de reportes almacenados en PostgreSQL. Permite filtrar por categoría, severidad, estado, comuna, búsqueda de texto (q) y distancia radial geográfica (Haversine).",
)
def list_citizen_reports(
    principal: CurrentSession,
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
        owner_id=_citizen_owner(principal),
    )
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [row_to_public_dict(r) for r in rows],
    }


@app.get(
    "/api/reports/by-code/{tracking_code}",
    response_model=ReportPublicResponse,
    tags=["Reportes ciudadanos"],
    summary="Consultar reporte por código de radicado",
    description="Consulta el detalle y diagnóstico de un reporte accesible para el titular de la sesión.",
)
def get_citizen_report_by_code(tracking_code: str, principal: CurrentSession):
    return row_to_public_dict(
        _visible_report(get_report_by_tracking_code(tracking_code, owner_id=_citizen_owner(principal)))
    )


@app.get(
    "/api/reports/{report_id}",
    response_model=ReportPublicResponse,
    tags=["Reportes ciudadanos"],
    summary="Obtener detalle de reporte por UUID",
    description="Retorna la información pública detallada de un reporte específico a partir de su identificador único universal (UUID).",
)
def get_citizen_report(report_id: UUID, principal: CurrentSession):
    return row_to_public_dict(
        _visible_report(get_report_raw(report_id, owner_id=_citizen_owner(principal)))
    )


@app.get(
    "/api/reports/{report_id}/photo",
    tags=["Fotografías y evidencias"],
    summary="Descargar o visualizar evidencia fotográfica",
    description="Entrega la fotografía limpia al titular del reporte o al personal administrativo.",
)
def get_citizen_report_photo(report_id: UUID, principal: CurrentSession):
    row = _visible_report(get_report_raw(report_id, include_events=False, owner_id=_citizen_owner(principal)))
    return _private_evidence(row.get("photo_path"), row.get("photo_mime"))


@app.get("/api/reports/{report_id}/audio", tags=["Fotografías y evidencias"])
def get_citizen_report_audio(report_id: UUID, principal: CurrentSession):
    row = _visible_report(get_report_raw(report_id, include_events=False, owner_id=_citizen_owner(principal)))
    return _private_evidence(row.get("audio_path"), row.get("audio_mime"))


def _private_evidence(stored_path: str | None, media_type: str | None) -> FileResponse:
    upload_dir = settings.UPLOAD_DIR.resolve()
    file_path = (upload_dir / Path(stored_path).name).resolve() if stored_path else None
    if file_path is None or not file_path.is_relative_to(upload_dir) or not file_path.is_file():
        raise CitizenValidationError(
            "La evidencia solicitada no está disponible.",
            status_code=404,
            code="EVIDENCE_NOT_FOUND",
        )
    return FileResponse(
        path=file_path,
        media_type=media_type or "application/octet-stream",
        headers={
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'",
        },
    )


@app.patch(
    "/api/reports/{report_id}/confirm",
    response_model=ReportPublicResponse,
    tags=["Reportes ciudadanos"],
    summary="Confirmar o corregir clasificación del reporte",
    description="Permite al ciudadano confirmar o corregir la categoría y severidad sugeridas por la IA tras el análisis inicial, transitionando el reporte al estado CONFIRMED.",
)
def confirm_citizen_report(
    report_id: UUID,
    payload: ReportConfirmRequest,
    principal: CitizenSession,
):
    clean_note = (
        sanitize_text(
            payload.human_override_note,
            field_name="nota de confirmación",
            max_len=500,
            required=False,
        )
        or None
    )
    updated = confirm_report_category(
        report_id,
        final_category=payload.final_category,
        final_severity=payload.final_severity,
        human_override_note=clean_note,
        owner_id=principal.id,
    )
    return row_to_public_dict(_visible_report(updated))


@app.patch(
    "/api/reports/{report_id}/status",
    response_model=ReportPublicResponse,
    tags=["Administración y gestión operativa"],
    summary="Actualizar estado operativo de un reporte (Requiere autorización)",
    description="Modifica el estado final de un reporte con permiso de gestión y confirmación humana explícita.",
)
def change_report_status(report_id: UUID, payload: ReportStatusUpdateRequest, principal: CaseAdminSession):
    if not payload.human_approved:
        raise CitizenValidationError(
            "Se requiere confirmación humana explícita para modificar el estado del reporte.",
            status_code=400,
            code="HUMAN_APPROVAL_REQUIRED",
        )
    clean_note = (
        sanitize_text(payload.note, field_name="nota de estado", max_len=500, required=False) or None
    )
    updated = update_report_status(report_id, status=payload.status, note=clean_note, actor_id=principal.id)
    return row_to_public_dict(_visible_report(updated))


@app.post(
    "/api/agent/query",
    response_model=AgentQueryResponse,
    tags=["Asistente ciudadano e IA"],
    summary="Consultar al asistente inteligente de CIVIA",
    description="Procesa consultas en lenguaje natural mediante el agente agéntico. Invoca herramientas SQL tipadas con límites de vueltas, tokens, timeout y aprobación humana obligatoria para escrituras críticas.",
)
def query_civia_agent(
    request: Request,
    payload: AgentQueryRequest,
    principal: CitizenSession,
    idempotency_key_header: str | None = Header(default=None, alias="Idempotency-Key"),
    operation_token_header: str | None = Header(default=None, alias="X-Operation-Token"),
):
    client_ip = get_trusted_client_ip(request)
    rate_limiter.check(f"agent:ip:{client_ip}")
    rate_limiter.check(f"agent:user:{principal.id}")
    clean_q = sanitize_text(
        payload.query,
        field_name="consulta",
        min_len=3,
        max_len=1000,
        required=True,
    )
    eff_client_token = operation_token_header or payload.operation_token
    eff_idemp_key = idempotency_key_header or payload.idempotency_key
    try:
        res = run_civia_agent(
            clean_q,
            max_iterations=payload.max_iterations,
            max_tokens_budget=payload.max_tokens_budget,
            tool_timeout_seconds=payload.tool_timeout_seconds or 4.0,
            total_timeout_seconds=payload.total_timeout_seconds,
            client_token=eff_client_token,
            idempotency_key=eff_idemp_key,
            owner_id=principal.id,
        )
    except IdempotencyConflictError as exc:
        raise CitizenValidationError(
            "La clave de solicitud ya se usó con datos diferentes.",
            status_code=409,
            code="IDEMPOTENCY_CONFLICT",
        ) from exc
    except OperationPendingError as exc:
        return {
            "answer": "Tu solicitud sigue pendiente. Puedes consultar su estado con el identificador.",
            "requires_human_approval": False,
            "pending_approval_id": None,
            "operation_id": str(exc.operation_id) if exc.operation_id else None,
            "operation_status": exc.status,
        }
    except TimeoutError:
        return {
            "answer": "El asistente no pudo responder a tiempo. Intenta de nuevo en unos minutos.",
        }
    return {
        "answer": res["answer"],
        "requires_human_approval": res.get("requires_human_approval", False),
        "pending_approval_id": res.get("pending_approval_id"),
        "operation_id": res.get("operation_id"),
        "operation_status": res.get("operation_status"),
    }


@app.get(
    "/api/operations/{operation_id}",
    response_model=OperationStatusResponse,
    tags=["Asistente ciudadano e IA"],
    summary="Consultar estado definitivo de una operación agéntica transaccional",
    description="Permite verificar operaciones del titular de la sesión y operaciones auditadas por la administración web.",
)
def get_operation_status(
    operation_id: UUID,
    principal: CurrentSession,
) -> OperationStatusResponse:
    rec = get_operation_record(operation_id)
    if rec is None or (principal.role != Role.WEB_ADMIN and rec.get("requester_id") != str(principal.id)):
        raise HTTPException(status_code=404, detail="Operación no encontrada.")
    if rec.get("status") in ("PENDING", "UNKNOWN"):
        rec = reconcile_operation(operation_id) or rec

    return OperationStatusResponse(
        operation_id=rec["operation_id"],
        operation_type=rec["operation_type"],
        status=rec["status"],
        target_id=rec.get("target_id"),
        result_payload=sanitize_credentials_deep(rec.get("result_payload")),
        error_message=rec.get("error_message") if principal.role == Role.WEB_ADMIN else None,
        created_at=rec["created_at"],
        updated_at=rec["updated_at"],
        reconciled=bool(rec.get("reconciled", False)),
    )


@app.get(
    "/api/admin/observability",
    dependencies=[Depends(require_web_admin)],
    tags=["Observabilidad y resiliencia"],
    summary="Consultar métricas de observabilidad y circuit breakers (Requiere autorización)",
    description="Consola de telemetría protegida. Retorna la cadena activa de proveedores de IA, estado de los interruptores de circuito, métricas P50/P90 de latencia y trazas técnicas sanitizadas sin secretos.",
)
def admin_get_observability(limit: int = Query(default=60, ge=1, le=300)) -> dict[str, Any]:
    summary = get_observability_summary(limit=limit)
    chain_public = [
        {"tier": c["tier"], "provider": c["provider"], "model": c["model"], "configured": bool(c["api_key"])}
        for c in get_provider_chain()
    ]
    return {
        "provider_chain": chain_public,
        "circuit_breakers": get_all_circuit_states(),
        "effective_fault_mode": get_effective_fault_mode(persisted=True) or "NONE",
        "observability": summary,
    }


@app.post(
    "/api/admin/fault-injection",
    tags=["Observabilidad y resiliencia"],
    summary="Simular fallas en caliente para pruebas de resiliencia (Requiere autorización)",
    description="Inyecta fallos sintéticos controlados (429, 503, TIMEOUT, INVALID_JSON, TOTAL) para auditar y verificar los mecanismos de fallback y conmutación automática entre proveedores.",
)
def admin_set_fault_injection(payload: FaultInjectionRequest, principal: WebAdminSession) -> dict[str, Any]:
    active = set_runtime_fault_override(payload.mode, persist=True)
    if payload.reset_circuits:
        reset_all_circuits()
    with get_conn(3000) as conn, conn.cursor() as cur:
        audit(cur, "system.configure_fault_mode", principal.id)
        conn.commit()
    return {
        "effective_fault_mode": get_effective_fault_mode(persisted=True) or "NONE",
        "runtime_override": active or "NONE",
        "circuit_breakers": get_all_circuit_states(),
    }


@app.get(
    "/api/admin/approvals",
    dependencies=[Depends(require_case_admin)],
    tags=["Aprobaciones humanas"],
    summary="Listar solicitudes de escritura crítica pendientes (Requiere autorización)",
    description="Retorna la lista de propuestas de modificación de estado generadas por el agente de IA que requieren aprobación humana obligatoria por un operador calificado.",
)
def admin_list_approvals(
    status: str | None = Query(default=None, max_length=16),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=1_000_000),
) -> dict[str, Any]:
    total, items = list_pending_approvals(status=status, limit=limit, offset=offset)
    return {"total": total, "items": items, "limit": limit, "offset": offset}


@app.post(
    "/api/admin/approvals/{approval_id}/decide",
    tags=["Aprobaciones humanas"],
    summary="Aprobar o rechazar solicitud de modificación crítica (Requiere autorización)",
    description="Aplica de forma atómica y de un solo uso la decisión humana sobre una propuesta de cambio de estado. Si se aprueba, actualiza el reporte en PostgreSQL; si se rechaza, cancela la propuesta.",
)
def admin_decide_approval(
    approval_id: UUID, payload: ApprovalDecisionRequest, principal: CaseAdminSession
) -> dict[str, Any]:
    updated = decide_pending_approval(
        approval_id,
        approve=payload.approve,
        decided_by=str(principal.id),
        reviewer_id=principal.id,
    )
    if not updated:
        raise CitizenValidationError(
            "No se encontró la solicitud de aprobación indicada.",
            status_code=404,
            code="APPROVAL_NOT_FOUND",
        )
    if updated.get("stale_conflict"):
        raise CitizenValidationError(
            "La solicitud ya no está disponible para esta decisión.",
            status_code=409,
            code="STALE_APPROVAL",
        )
    return {"status": "ok", "approval": updated}


@app.post(
    "/api/admin/seed",
    dependencies=[Depends(require_web_admin)],
    tags=["Administración y gestión operativa"],
    summary="Sembrar o reiniciar catálogo sintético de prueba (Requiere autorización)",
    description="Inicializa o actualiza los 10 reportes sintéticos de demostración con evidencias fotorrealistas en Cali bajo almacenamiento inmutable Content-Addressed.",
)
def admin_seed_reports(force_reset: bool = Query(default=False)) -> dict[str, Any]:
    return seed_synthetic_reports(force_reset=force_reset)


@app.get(
    "/api/reports/{report_id}/events",
    response_model=list[ReportEventPublic],
    tags=["Seguimiento y trazabilidad"],
    summary="Obtener historial de eventos de un reporte por UUID",
    description="Retorna la cronología pública y transparente de actuaciones (registro, análisis IA, confirmación, cambios de estado y notas públicas) asociadas al reporte.",
)
def get_report_events_by_id(report_id: UUID, principal: CurrentSession):
    row = _visible_report(get_report_raw(report_id, owner_id=_citizen_owner(principal)))
    return row_to_public_dict(row)["events"]


@app.get(
    "/api/reports/by-code/{tracking_code}/events",
    response_model=list[ReportEventPublic],
    tags=["Seguimiento y trazabilidad"],
    summary="Obtener historial de eventos de un reporte por código de radicado",
    description="Permite al ciudadano visualizar la línea de tiempo completa de su solicitud ingresando su número de radicado oficial.",
)
def get_report_events_by_tracking_code(tracking_code: str, principal: CurrentSession):
    row = _visible_report(get_report_by_tracking_code(tracking_code, owner_id=_citizen_owner(principal)))
    return row_to_public_dict(row)["events"]


@app.get(
    "/api/admin/notifications",
    response_model=AdminNotificationsResponse,
    dependencies=[Depends(require_case_admin)],
    tags=["Administración y gestión operativa"],
    summary="Listar notificaciones internas para operadores (Requiere autorización)",
    description="Bandeja de alertas internas generadas automáticamente al registrarse reportes ciudadanos. Permite filtrar por leídas/no leídas y por tipo de reporte (ciudadano o sintético).",
)
def admin_get_notifications(
    limit: int = Query(default=50, ge=1, le=200),
    unread_only: bool = Query(default=False),
    filter_type: str = Query(default="ALL"),
) -> dict[str, Any]:
    return list_admin_notifications(limit=limit, unread_only=unread_only, filter_type=filter_type)


@app.patch(
    "/api/admin/notifications/{notification_id}/read",
    dependencies=[Depends(require_case_admin)],
    tags=["Administración y gestión operativa"],
    summary="Marcar notificación interna como leída (Requiere autorización)",
    description="Actualiza el estado de lectura de una notificación interna en la bandeja de administración.",
)
def admin_mark_notification_as_read(notification_id: UUID) -> dict[str, Any]:
    ok = mark_admin_notification_read(notification_id)
    if not ok:
        raise CitizenValidationError(
            "No se encontró la notificación o ya fue procesada.",
            status_code=404,
            code="NOTIFICATION_NOT_FOUND",
        )
    return {"status": "ok", "id": str(notification_id)}


@app.post(
    "/api/admin/notifications/mark-all-read",
    dependencies=[Depends(require_case_admin)],
    tags=["Administración y gestión operativa"],
    summary="Marcar todas las notificaciones internas como leídas (Requiere autorización)",
    description="Marca simultáneamente como leídas todas las notificaciones pendientes en la bandeja de administración.",
)
def admin_mark_all_notifications_as_read() -> dict[str, Any]:
    count = mark_all_admin_notifications_read()
    return {"status": "ok", "updated_count": count}


@app.post(
    "/api/admin/reports/{report_id}/management",
    response_model=ReportPublicResponse,
    tags=["Administración y gestión operativa"],
    summary="Asignar dependencia municipal y gestionar notas (Requiere autorización)",
    description="Permite a los operadores administrativos asignar una dependencia responsable (ej. Secretaría de Infraestructura, Dagma), registrar notas públicas de seguimiento y notas internas confidenciales.",
)
def admin_update_report_management(
    report_id: UUID,
    payload: ReportManagementUpdateRequest,
    principal: CaseAdminSession,
):
    updated = update_report_management(
        report_id,
        assigned_to=payload.assigned_to,
        admin_review_status=payload.admin_review_status,
        public_note=payload.public_note,
        internal_note=payload.internal_note,
        actor_id=principal.id,
    )
    if not updated:
        raise CitizenValidationError(
            "No se encontró el reporte indicado para gestión.",
            status_code=404,
            code="REPORT_NOT_FOUND",
        )
    return row_to_public_dict(updated)


@app.get("/api/admin/reports/{report_id}/internal-notes", tags=["Administración y gestión operativa"])
def admin_get_internal_notes(
    report_id: UUID,
    principal: CaseAdminSession,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=1_000_000),
) -> dict[str, Any]:
    _visible_report(get_report_raw(report_id, include_events=False))
    with get_conn(3000) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT note, created_at FROM report_internal_notes WHERE report_id = %s
            ORDER BY created_at DESC, id DESC LIMIT %s OFFSET %s;
            """,
            (report_id, limit, offset),
        )
        return {"items": cur.fetchall(), "limit": limit, "offset": offset}


@app.get("/api/admin/system", dependencies=[Depends(require_web_admin)], tags=["Observabilidad y resiliencia"])
def admin_system_status() -> dict[str, Any]:
    return _health_payload()


@app.get("/api/admin/queue", dependencies=[Depends(require_web_admin)], tags=["Observabilidad y resiliencia"])
def admin_queue_status() -> dict[str, Any]:
    return queue_status()


@app.get("/api/admin/queue/dead-letter", dependencies=[Depends(require_web_admin)], tags=["Observabilidad y resiliencia"])
def admin_queue_dead_letter(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=1_000_000),
) -> dict[str, Any]:
    return {"items": list_dead_letters(limit=limit, offset=offset), "limit": limit, "offset": offset}


@app.post("/api/admin/queue/dead-letter/{job_id}/requeue", status_code=202, tags=["Observabilidad y resiliencia"])
def admin_requeue_dead_letter(
    job_id: UUID,
    principal: WebAdminSession,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", min_length=8, max_length=128),
) -> dict[str, str]:
    if not requeue_dead_letter(job_id, principal.id, idempotency_key=idempotency_key):
        raise CitizenValidationError(
            "El trabajo no está disponible para reintentar.", status_code=404, code="JOB_NOT_FOUND"
        )
    return {"status": "accepted"}
