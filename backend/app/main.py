from contextlib import asynccontextmanager
import logging
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import Depends, FastAPI, File, Form, Header, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from app.config import settings
from app.db import check_db_health, run_migrations
from app.repository import (
    confirm_report_category,
    create_report,
    get_report_by_tracking_code,
    get_report_raw,
    get_reports_summary_stats,
    list_reports,
    row_to_public_dict,
    update_report_status,
)
from app.schemas import (
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
    if not x_admin_token or x_admin_token != settings.ADMIN_TOKEN:
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
    photo: UploadFile = File(...),
    audio: UploadFile | None = File(default=None),
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
    photo_meta = validate_and_store_photo(raw_photo, declared_filename=photo.filename)

    audio_meta = None
    if audio is not None and audio.filename:
        raw_audio = await audio.read()
        if raw_audio:
            audio_meta = validate_and_store_audio(raw_audio, declared_filename=audio.filename)

    row = create_report(
        title=clean_title,
        description=clean_desc,
        latitude=lat,
        longitude=lon,
        in_service_area=in_service_area,
        comuna=clean_comuna,
        neighborhood=clean_neighborhood,
        address_hint=clean_address,
        photo_meta=photo_meta,
        audio_meta=audio_meta,
    )
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
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "public, max-age=3600"},
    )


@app.patch("/api/reports/{report_id}/confirm", response_model=ReportPublicResponse)
def confirm_citizen_report(report_id: UUID, payload: ReportConfirmRequest):
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
    updated = confirm_report_category(
        report_id,
        final_category=payload.final_category,
        final_severity=payload.final_severity,
        human_override_note=clean_note,
    )
    assert updated is not None
    return row_to_public_dict(updated)


@app.patch("/api/reports/{report_id}/status", response_model=ReportPublicResponse)
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


@app.post("/api/admin/seed", dependencies=[Depends(verify_admin_token)])
def admin_seed_reports(force_reset: bool = Query(default=False)) -> dict[str, Any]:
    return seed_synthetic_reports(force_reset=force_reset)
