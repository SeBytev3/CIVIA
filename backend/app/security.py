from collections import defaultdict, deque
import hashlib
import io
import ipaddress
import math
import os
from pathlib import Path
import re
import time
import uuid
import wave
from typing import Any

from PIL import Image, UnidentifiedImageError
from starlette.requests import Request

from app.config import settings


class CitizenValidationError(Exception):
    """Error de validación seguro para mostrar al ciudadano (sin trazas internas)."""

    def __init__(self, message: str, status_code: int = 422, code: str = "VALIDATION_ERROR"):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


_HTML_TAG_RE = re.compile(r"<[^>]+>")
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_CO_PHONE_RE = re.compile(r"\b(?:3\d{2}[\s.-]?\d{3}[\s.-]?\d{4})\b")


def sanitize_text(
    value: str | None,
    *,
    field_name: str,
    min_len: int = 0,
    max_len: int = 2000,
    required: bool = True,
) -> str:
    if value is None:
        if required:
            raise CitizenValidationError(f"El campo '{field_name}' es obligatorio.")
        return ""

    cleaned = _CONTROL_CHARS_RE.sub("", value)
    cleaned = _HTML_TAG_RE.sub("", cleaned)
    # Minimización de datos personales (PII): ocultar correos y celulares accidentales
    cleaned = _EMAIL_RE.sub("[CORREO_PROTEGIDO]", cleaned)
    cleaned = _CO_PHONE_RE.sub("[TELEFONO_PROTEGIDO]", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if required and len(cleaned) < min_len:
        raise CitizenValidationError(
            f"El campo '{field_name}' debe tener al menos {min_len} caracteres válidos."
        )
    if len(cleaned) > max_len:
        raise CitizenValidationError(
            f"El campo '{field_name}' supera el máximo permitido de {max_len} caracteres."
        )
    return cleaned


def validate_coordinates(latitude: float, longitude: float) -> tuple[float, float, bool]:
    if (
        latitude is None
        or longitude is None
        or math.isnan(latitude)
        or math.isnan(longitude)
        or math.isinf(latitude)
        or math.isinf(longitude)
    ):
        raise CitizenValidationError("Las coordenadas GPS proporcionadas no son números válidos.")

    if not (-90.0 <= latitude <= 90.0):
        raise CitizenValidationError("La latitud debe estar entre -90.0 y 90.0 grados.")
    if not (-180.0 <= longitude <= 180.0):
        raise CitizenValidationError("La longitud debe estar entre -180.0 y 180.0 grados.")

    if abs(latitude) < 1e-5 and abs(longitude) < 1e-5:
        raise CitizenValidationError(
            "Las coordenadas (0, 0) no corresponden a una ubicación válida del reporte."
        )

    in_service_area = (
        settings.SERVICE_LAT_MIN <= latitude <= settings.SERVICE_LAT_MAX
        and settings.SERVICE_LON_MIN <= longitude <= settings.SERVICE_LON_MAX
    )
    return round(float(latitude), 6), round(float(longitude), 6), in_service_area


def _detect_image_magic(raw_bytes: bytes) -> tuple[str, str, str] | None:
    """Verifica firma binaria real (magic bytes): retorna (mime, pil_format, ext)."""
    if raw_bytes.startswith(b"\xff\xd8\xff"):
        return ("image/jpeg", "JPEG", "jpg")
    if raw_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return ("image/png", "PNG", "png")
    if len(raw_bytes) >= 12 and raw_bytes[:4] == b"RIFF" and raw_bytes[8:12] == b"WEBP":
        return ("image/webp", "WEBP", "webp")
    return None


def _atomic_write_bytes(target_dir: Path, final_name: str, data: bytes) -> Path:
    """
    Escribe bytes primero en un archivo temporal dentro de target_dir, verifica que
    el tamaño escrito coincida exactamente con len(data) y lo promueve atómicamente
    al destino final. Si ocurre cualquier fallo o escritura parcial, elimina tanto
    el archivo temporal como el archivo destino antes de propagar la excepción.
    Valida la capacidad revocable de ejecución antes de escribir y de promover (M-03).
    """
    from app.db import atomic_publish_file, check_execution_capability_or_raise

    check_execution_capability_or_raise("escritura en almacenamiento")
    target_dir.mkdir(parents=True, exist_ok=True)
    final_path = target_dir / final_name
    staging_path = target_dir / f".tmp_{uuid.uuid4().hex}_{final_name}"
    try:
        staging_path.write_bytes(data)
        if not staging_path.exists() or staging_path.stat().st_size != len(data):
            raise OSError("Escritura parcial o incompleta detectada en archivo temporal.")
        atomic_publish_file(staging_path, final_path)
        return final_path
    except BaseException:
        try:
            staging_path.unlink(missing_ok=True)
        except OSError:
            pass
        try:
            final_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def validate_and_store_photo(
    raw_bytes: bytes,
    declared_filename: str | None = None,
    upload_dir: Path | None = None,
) -> dict[str, Any]:
    if not raw_bytes:
        raise CitizenValidationError("La fotografía de evidencia está vacía.", status_code=400)

    if len(raw_bytes) > settings.MAX_PHOTO_BYTES:
        raise CitizenValidationError(
            "La fotografía supera el tamaño máximo permitido de 5 MB.",
            status_code=413,
            code="FILE_TOO_LARGE",
        )

    magic = _detect_image_magic(raw_bytes)
    if magic is None:
        raise CitizenValidationError(
            "Formato de imagen no permitido. Solo se aceptan fotografías JPEG, PNG o WEBP verificadas.",
            status_code=415,
            code="UNSUPPORTED_MEDIA_TYPE",
        )

    mime_type, pil_format, ext = magic

    try:
        with Image.open(io.BytesIO(raw_bytes)) as img:
            img.verify()
        with Image.open(io.BytesIO(raw_bytes)) as img:
            width, height = img.size
            if width < settings.MIN_IMAGE_DIM or height < settings.MIN_IMAGE_DIM:
                raise CitizenValidationError(
                    f"La fotografía es demasiado pequeña ({width}x{height} px). Debe ser de al menos {settings.MIN_IMAGE_DIM}x{settings.MIN_IMAGE_DIM} píxeles.",
                    status_code=422,
                )
            if width > settings.MAX_IMAGE_DIM or height > settings.MAX_IMAGE_DIM:
                raise CitizenValidationError(
                    f"Las dimensiones de la imagen ({width}x{height} px) exceden el límite de seguridad.",
                    status_code=422,
                )

            # Re-codificación limpia sin metadatos EXIF (minimización de datos personales/privacidad)
            clean_buffer = io.BytesIO()
            if pil_format == "JPEG":
                clean_img = img.convert("RGB")
                clean_img.save(clean_buffer, format="JPEG", quality=88)
            elif pil_format == "PNG":
                clean_img = img.convert("RGBA" if img.mode == "RGBA" else "RGB")
                clean_img.save(clean_buffer, format="PNG")
            else:
                clean_img = img.convert("RGB")
                clean_img.save(clean_buffer, format="WEBP", quality=88)
            sanitized_bytes = clean_buffer.getvalue()
    except CitizenValidationError:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise CitizenValidationError(
            "El archivo adjunto no es una imagen válida o está corrupto.",
            status_code=415,
            code="INVALID_IMAGE",
        ) from exc

    target_dir = upload_dir or settings.UPLOAD_DIR
    safe_name = f"photo_{uuid.uuid4().hex}.{ext}"
    _atomic_write_bytes(target_dir, safe_name, sanitized_bytes)

    sha256_hex = hashlib.sha256(sanitized_bytes).hexdigest()
    return {
        "photo_path": safe_name,
        "photo_mime": mime_type,
        "photo_size_bytes": len(sanitized_bytes),
        "photo_width": width,
        "photo_height": height,
        "photo_sha256": sha256_hex,
    }


def _detect_audio_magic(raw_bytes: bytes) -> tuple[str, str] | None:
    if len(raw_bytes) >= 44 and raw_bytes[:4] == b"RIFF" and raw_bytes[8:12] == b"WAVE":
        return ("audio/wav", "wav")
    if len(raw_bytes) >= 64 and raw_bytes.startswith(b"OggS"):
        return ("audio/ogg", "ogg")
    if len(raw_bytes) >= 64 and raw_bytes.startswith(b"\x1a\x45\xdf\xa3"):
        return ("audio/webm", "webm")
    if len(raw_bytes) >= 10 and (
        (raw_bytes.startswith(b"ID3") and raw_bytes[3] <= 4)
        or (raw_bytes[0] == 0xFF and (raw_bytes[1] & 0xE0) == 0xE0)
    ):
        return ("audio/mpeg", "mp3")
    return None


def _validate_mp3_payload(raw_bytes: bytes) -> tuple[int, float]:
    """
    Verifica que el archivo contenga tramas de audio MP3 reales más allá del encabezado ID3 (M-01).
    Retorna (tamaño_payload_audio, duracion_estimada_segundos).
    """
    offset = 0
    if raw_bytes.startswith(b"ID3") and len(raw_bytes) >= 10:
        ver = raw_bytes[3]
        if ver > 4:
            raise CitizenValidationError("Versión de ID3 no compatible.", status_code=415, code="INVALID_AUDIO")
        tag_size = (
            ((raw_bytes[6] & 0x7F) << 21)
            | ((raw_bytes[7] & 0x7F) << 14)
            | ((raw_bytes[8] & 0x7F) << 7)
            | (raw_bytes[9] & 0x7F)
        )
        offset = 10 + tag_size
        if raw_bytes[5] & 0x10:
            offset += 10

    payload = raw_bytes[offset:]
    if len(payload) < 256:
        raise CitizenValidationError(
            "El archivo de audio no contiene tramas de audio válidas (payload insuficiente).",
            status_code=415,
            code="INVALID_AUDIO",
        )

    # Buscar sincronización de trama MPEG (11 bits en 1: 0xFF seguido de (byte & 0xE0) == 0xE0)
    has_sync = False
    for i in range(min(len(payload) - 1, 4096)):
        if payload[i] == 0xFF and (payload[i + 1] & 0xE0) == 0xE0:
            layer_bits = (payload[i + 1] >> 1) & 0x03
            if layer_bits != 0:
                has_sync = True
                break

    if not has_sync:
        raise CitizenValidationError(
            "El archivo de audio no contiene tramas de audio MP3 reproducibles.",
            status_code=415,
            code="INVALID_AUDIO",
        )

    duration = round(max(0.1, len(payload) / 16000.0), 2)
    return len(payload), duration


def validate_and_store_audio(
    raw_bytes: bytes,
    declared_filename: str | None = None,
    upload_dir: Path | None = None,
) -> dict[str, Any]:
    if not raw_bytes:
        raise CitizenValidationError("El archivo de audio está vacío.", status_code=400)

    if len(raw_bytes) > settings.MAX_AUDIO_BYTES:
        raise CitizenValidationError(
            "El archivo de audio supera el límite máximo de 5 MB.",
            status_code=413,
            code="AUDIO_TOO_LARGE",
        )

    magic = _detect_audio_magic(raw_bytes)
    if magic is None:
        raise CitizenValidationError(
            "Formato de audio no permitido. Use WAV, MP3, OGG o WEBM.",
            status_code=415,
            code="UNSUPPORTED_AUDIO_TYPE",
        )

    mime_type, ext = magic
    duration_seconds = 10.0

    if ext == "wav":
        try:
            with wave.open(io.BytesIO(raw_bytes), "rb") as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                if rate <= 0 or frames <= 0:
                    raise CitizenValidationError("Audio WAV sin tramas de audio reproducibles.", status_code=415)
                duration_seconds = round(frames / float(rate), 2)
                if duration_seconds < 0.1:
                    raise CitizenValidationError("Audio WAV con duración inferior al mínimo reproducible.", status_code=415)
        except CitizenValidationError:
            raise
        except Exception as exc:
            raise CitizenValidationError("El archivo WAV está corrupto o es inválido.", status_code=415) from exc
    elif ext == "mp3":
        _, duration_seconds = _validate_mp3_payload(raw_bytes)
    else:
        # Para OGG / WEBM verificar que no sean archivos vacíos o de solo relleno
        if len(raw_bytes) < 512:
            raise CitizenValidationError("El archivo de audio comprimido no contiene datos suficientes.", status_code=415)
        duration_seconds = round(max(0.1, len(raw_bytes) / 16000.0), 2)

    if duration_seconds > settings.MAX_AUDIO_DURATION_SECONDS:
        raise CitizenValidationError(
            f"La nota de voz dura {duration_seconds:.1f}s y supera el máximo permitido de 60 segundos.",
            status_code=422,
            code="AUDIO_TOO_LONG",
        )

    target_dir = upload_dir or settings.UPLOAD_DIR
    safe_name = f"audio_{uuid.uuid4().hex}.{ext}"
    _atomic_write_bytes(target_dir, safe_name, raw_bytes)

    return {
        "audio_path": safe_name,
        "audio_mime": mime_type,
        "audio_size_bytes": len(raw_bytes),
        "audio_duration_seconds": max(0.1, duration_seconds),
    }


def get_trusted_proxy_networks() -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    nets: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    raw = getattr(settings, "TRUSTED_PROXIES", "") or ""
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            if "/" in item:
                nets.append(ipaddress.ip_network(item, strict=False))
            else:
                addr = ipaddress.ip_address(item)
                nets.append(ipaddress.ip_network(f"{addr}/32" if addr.version == 4 else f"{addr}/128"))
        except ValueError:
            pass
    return nets


def is_trusted_proxy_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str.strip())
        return any(ip in net for net in get_trusted_proxy_networks())
    except ValueError:
        return False


def get_trusted_client_ip(request: Request) -> str:
    """
    Resuelve de forma segura la IP real del cliente evitando spoofing (M-06).
    Si la conexión no proviene de un proxy inverso confiable explícito, usa la IP del peer directamente
    e ignora por completo cualquier cabecera X-Forwarded-For o X-Real-IP enviada por el cliente.
    Si proviene de un proxy confiable, extrae la IP real verificando la cadena de confianza.
    """
    peer_ip = request.client.host if request.client else "unknown"
    if not is_trusted_proxy_ip(peer_ip):
        return peer_ip

    x_real = request.headers.get("x-real-ip")
    if x_real and x_real.strip():
        cand = x_real.strip()
        if not is_trusted_proxy_ip(cand):
            return cand

    xff = request.headers.get("x-forwarded-for")
    if xff:
        parts = [p.strip() for p in xff.split(",") if p.strip()]
        for cand in reversed(parts):
            if not is_trusted_proxy_ip(cand):
                return cand
        if parts:
            return parts[0]

    return peer_ip


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, client_key: str) -> None:
        now = time.monotonic()
        window = settings.RATE_LIMIT_WINDOW_SECONDS
        max_req = settings.RATE_LIMIT_MAX_REQUESTS
        q = self._hits[client_key]
        while q and (now - q[0]) > window:
            q.popleft()
        if len(q) >= max_req:
            raise CitizenValidationError(
                "Ha realizado demasiadas solicitudes en poco tiempo. Por favor espere un minuto e intente nuevamente.",
                status_code=429,
                code="RATE_LIMIT_EXCEEDED",
            )
        q.append(now)

    def reset(self) -> None:
        self._hits.clear()


rate_limiter = RateLimiter()
