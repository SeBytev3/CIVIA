from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class ReportLookup(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    identificador: Annotated[str, Field(
        min_length=8, max_length=64,
        pattern=r"^(?:CIV-[0-9]{4}-[A-Za-z0-9]+|[a-fA-F0-9-]{36})$",
    )]


class ReportFilters(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    category: Literal["HUECO", "BASURAS", "TALA", "QUEMA", "OTRO"] | None = None
    severity: Literal["BAJA", "MEDIA", "ALTA", "CRITICA"] | None = None
    status: Literal[
        "PENDING_ANALYSIS", "ANALYZED_PENDING_CONFIRMATION", "CONFIRMED",
        "IN_REVIEW", "RESOLVED", "REJECTED",
    ] | None = None
    comuna: Annotated[str, Field(pattern=r"^Comuna [0-9]{1,2}$")] | None = None
    limit: Annotated[int, Field(ge=1, le=20)] = 10


class ApprovalRequest(ReportLookup):
    nuevo_estado: Literal["IN_REVIEW", "RESOLVED", "REJECTED", "CONFIRMED"]
    motivo: Annotated[str, Field(min_length=5, max_length=500)]


INPUT_MODELS = {
    "consultar_reportes": ReportFilters,
    "obtener_reporte": ReportLookup,
    "clasificar_evidencia": ReportLookup,
    "proponer_actualizacion_critica": ApprovalRequest,
}
