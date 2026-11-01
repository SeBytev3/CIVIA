from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

ReportCategory = Literal["HUECO", "BASURAS", "TALA", "QUEMA", "OTRO"]
ReportSeverity = Literal["BAJA", "MEDIA", "ALTA", "CRITICA"]
ReportStatus = Literal[
    "PENDING_ANALYSIS",
    "ANALYZED_PENDING_CONFIRMATION",
    "CONFIRMED",
    "IN_REVIEW",
    "RESOLVED",
    "REJECTED",
]


class AIAnalysisContract(BaseModel):
    category: ReportCategory = Field(
        description="Categoría ambiental o vial detectada: HUECO, BASURAS, TALA, QUEMA u OTRO."
    )
    severity: ReportSeverity = Field(
        description="Nivel de severidad estimado según riesgo ciudadano o ambiental: BAJA, MEDIA, ALTA o CRITICA."
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confianza de la clasificación entre 0.0 y 1.0.",
    )
    summary: str = Field(
        min_length=10,
        max_length=450,
        description="Explicación breve, objetiva y clara para el ciudadano (máximo 450 caracteres).",
    )
    keywords: list[str] = Field(
        default_factory=list,
        max_length=8,
        description="Palabras clave observadas en la evidencia.",
    )


class ReportConfirmRequest(BaseModel):
    final_category: ReportCategory
    final_severity: ReportSeverity | None = None
    human_override_note: str | None = Field(default=None, max_length=500)


class ReportStatusUpdateRequest(BaseModel):
    status: Literal["CONFIRMED", "IN_REVIEW", "RESOLVED", "REJECTED"]
    human_approved: bool = Field(
        description="Debe ser True para autorizar el cambio de estado sobre el registro."
    )
    note: str | None = Field(default=None, max_length=500)


class ReportPublicResponse(BaseModel):
    id: UUID
    tracking_code: str
    title: str
    description: str
    latitude: float
    longitude: float
    in_service_area: bool
    comuna: str | None = None
    neighborhood: str | None = None
    address_hint: str | None = None
    photo_url: str
    photo_mime: str
    photo_width: int
    photo_height: int
    has_audio: bool = False
    audio_transcript: str | None = None
    ai_category: ReportCategory | None = None
    ai_severity: ReportSeverity | None = None
    ai_confidence: float | None = None
    ai_summary: str | None = None
    ai_keywords: list[str] = Field(default_factory=list)
    final_category: ReportCategory | None = None
    final_severity: ReportSeverity | None = None
    effective_category: ReportCategory | None = None
    effective_severity: ReportSeverity | None = None
    human_confirmed: bool
    human_override_note: str | None = None
    status: ReportStatus
    status_message: str
    distance_km: float | None = None
    is_synthetic: bool = False
    created_at: datetime
    updated_at: datetime


class ReportListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[ReportPublicResponse]
