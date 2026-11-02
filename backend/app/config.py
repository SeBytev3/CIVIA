import os
from pathlib import Path
import re
import secrets


class Settings:
    PROJECT_NAME: str = "CIVIA API"
    VERSION: str = "0.2.0"
    PHASE: str = os.getenv("CIVIA_PHASE", "mvp")

    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://civia:local_dev_change_me@db:5432/civia",
    )

    UPLOAD_DIR: Path = Path(os.getenv("UPLOAD_DIR", "/app/data/uploads"))
    MIGRATIONS_DIR: Path = Path(
        os.getenv("MIGRATIONS_DIR", str(Path(__file__).resolve().parent.parent / "migrations"))
    )

    MAX_PHOTO_BYTES: int = 5 * 1024 * 1024  # 5 MB
    MIN_IMAGE_DIM: int = 32
    MAX_IMAGE_DIM: int = 8192

    MAX_AUDIO_BYTES: int = 5 * 1024 * 1024  # 5 MB
    MAX_AUDIO_DURATION_SECONDS: float = 60.0

    # Valle del Cauca / Cali bounding box aproximado
    SERVICE_LAT_MIN: float = 2.90
    SERVICE_LAT_MAX: float = 5.10
    SERVICE_LON_MIN: float = -77.60
    SERVICE_LON_MAX: float = -75.60

    # Rate limit por IP para creación de reportes
    RATE_LIMIT_MAX_REQUESTS: int = int(os.getenv("RATE_LIMIT_MAX_REQUESTS", "30"))
    RATE_LIMIT_WINDOW_SECONDS: int = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))

    # Auto-seed de datos sintéticos identificados al arrancar si la tabla está vacía
    AUTO_SEED_SYNTHETIC: bool = os.getenv("AUTO_SEED_SYNTHETIC", "true").lower() in ("1", "true", "yes")

    # Token de administración para observabilidad protegida y operaciones admin (sin valor por defecto)
    ADMIN_TOKEN: str = os.getenv("ADMIN_TOKEN", "")

    # Configuración de proveedores IA (Fase D)
    GOOGLE_API_KEY_PRIMARY: str = os.getenv("GOOGLE_API_KEY_PRIMARY", "")
    GOOGLE_API_KEY_SECONDARY: str = os.getenv("GOOGLE_API_KEY_SECONDARY", "")
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    AI_PRIMARY_MODEL: str = os.getenv("AI_PRIMARY_MODEL", "gemini-3.8-flash")
    AI_FALLBACK_MODEL: str = os.getenv("AI_FALLBACK_MODEL", "qwen/qwen3.8-27b")
    AI_TERTIARY_MODEL: str = os.getenv("AI_TERTIARY_MODEL", "gemini-3.5-flash-lite")
    AI_TIMEOUT_SECONDS: float = float(os.getenv("AI_TIMEOUT_SECONDS", "15"))
    AI_MAX_RETRIES: int = int(os.getenv("AI_MAX_RETRIES", "2"))
    AGENT_MAX_ITERATIONS: int = int(os.getenv("AGENT_MAX_ITERATIONS", "5"))
    AGENT_MAX_TOKENS: int = int(os.getenv("AGENT_MAX_TOKENS", "6000"))

    @property
    def falla_forzada(self) -> str:
        return os.getenv("FALLA_FORZADA", "").strip().upper()


WEAK_ADMIN_TOKENS: set[str] = {
    "",
    "civia-admin-demo-2026",
    "civia_admintoken_2026_demo!",
    "admin",
    "password",
    "secret",
    "changeme",
    "local_dev_change_me",
    "123456",
    "admin123",
    "test",
    "demo",
    "replace_with_generated_admin_token",
}

_WEAK_SUBSTRINGS: tuple[str, ...] = (
    "civia",
    "admintoken",
    "admin",
    "prueba",
    "change_me",
    "changeme",
    "password",
    "passwd",
    "secret",
    "secreto",
    "token",
    "clave",
    "replace_with",
    "default",
    "example",
    "sample",
    "localdev",
    "local_dev",
    "operator",
    "operador",
    "valle",
    "momento",
    "evaluativo",
    "qwerty",
    "asdfgh",
    "zxcvbn",
)

_DELIMITED_CONTEXT_TERMS_RE = re.compile(
    r"(?:^|[_.\-:])(?:demo|test|testing|cali|role|prod|staging|dev|2024|2025|2026|2027)(?:$|[_.\-:!])",
    re.IGNORECASE,
)

_URLSAFE_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{32,256}$")
_PURE_TITLE_OR_CAMEL_SEG_RE = re.compile(r"^[A-Z][a-z]{2,}(?:[A-Z][a-z]{2,})*$")
_DELIMITED_YEAR_RE = re.compile(r"(?:^|[^0-9])(?:19|20)\d{2}(?:$|[^0-9])")

_KEYBOARD_ROWS: tuple[str, ...] = (
    "01234567890",
    "09876543210",
    "abcdefghijklmnopqrstuvwxyz",
    "zyxwvutsrqponmlkjihgfedcba",
    "qwertyuiop",
    "poiuytrewq",
    "asdfghjkl",
    "lkjhgfdsa",
    "zxcvbnm",
    "mnbvcxz",
)


def _has_sequential_run(value: str, run_len: int = 6) -> bool:
    low = value.lower()
    if len(low) < run_len:
        return False
    for row in _KEYBOARD_ROWS:
        for i in range(len(row) - run_len + 1):
            if row[i : i + run_len] in low:
                return True
    for i in range(len(low) - run_len + 1):
        window = low[i : i + run_len]
        diffs = [ord(window[j + 1]) - ord(window[j]) for j in range(run_len - 1)]
        if all(d == 1 for d in diffs) or all(d == -1 for d in diffs) or all(d == 0 for d in diffs):
            return True
    return False


def _has_repeated_pattern(value: str) -> bool:
    n = len(value)
    low = value.lower()
    # 1. Periodicidad global: la cadena completa es repetición de un prefijo de periodo p
    for p in range(1, (n // 2) + 1):
        repeated = (low[:p] * ((n // p) + 1))[:n]
        if low == repeated:
            return True
    # 2. Repetición de bloques de longitud >= 3 tres o más veces, o bloques adyacentes de longitud >= 4
    for k in range(3, min(13, (n // 2) + 1)):
        for i in range(n - k + 1):
            sub = low[i : i + k]
            if low.count(sub) >= 3:
                return True
            if k >= 4 and i + 2 * k <= n and low[i + k : i + 2 * k] == sub:
                return True
    return False


def _has_contextual_or_phrase_pattern(value: str) -> bool:
    low = value.lower()
    alnum_low = re.sub(r"[^a-z0-9]", "", low)
    if any(w in low or w in alnum_low for w in _WEAK_SUBSTRINGS):
        return True
    if _DELIMITED_CONTEXT_TERMS_RE.search(value):
        return True
    # Frases compuestas por segmentos separados por '_' o '-' donde >= 2 segmentos son palabras TitleCase/CamelCase puras
    raw_segments = [re.sub(r"[!@#$%^&*+=?~]+$", "", seg) for seg in re.split(r"[_.\-:]+", value) if seg]
    title_segments = sum(1 for seg in raw_segments if _PURE_TITLE_OR_CAMEL_SEG_RE.match(seg))
    if len(raw_segments) >= 3 and title_segments >= 2:
        return True
    if _DELIMITED_YEAR_RE.search(value) and title_segments >= 1:
        return True
    return False


def is_strong_admin_token(token: str | None) -> bool:
    """
    Política de validación de ADMIN_TOKEN:
    - El mecanismo estándar de instalación es la generación local con CSPRNG mediante
      secrets.token_urlsafe(32) (>= 32 caracteres URL-safe base64).
    - Rechaza tokens vacíos, cortos (< 32 caracteres), con baja variedad de símbolos (< 12),
      secuencias numéricas/alfabéticas/teclado, patrones periódicos y credenciales contextuales
      o de demostración construidas con nombre del proyecto, rol, año o etiquetas Demo/Test.
    - Nota técnica: ningún filtro sobre una cadena estática puede demostrar matemáticamente
      que un valor externo arbitrario proviene de un CSPRNG; la seguridad depende de seguir el
      procedimiento de generación con secrets.token_urlsafe(32).
    """
    if not token or not isinstance(token, str):
        return False
    cleaned = token.strip()
    if len(cleaned) < 32 or len(cleaned) > 256:
        return False
    if any(ch.isspace() for ch in cleaned):
        return False
    if len(set(cleaned)) < 12:
        return False

    low = cleaned.lower()
    if low in WEAK_ADMIN_TOKENS:
        return False

    allow_custom_format = os.getenv("ADMIN_TOKEN_ALLOW_CUSTOM_FORMAT", "false").lower() in (
        "1",
        "true",
        "yes",
    )
    if not allow_custom_format and not _URLSAFE_TOKEN_RE.match(cleaned):
        return False

    if _has_contextual_or_phrase_pattern(cleaned):
        return False

    has_lower = any("a" <= c <= "z" for c in cleaned)
    has_upper = any("A" <= c <= "Z" for c in cleaned)
    has_digit = any("0" <= c <= "9" for c in cleaned)
    has_symbol = any(not c.isalnum() for c in cleaned)
    char_classes = sum((has_lower, has_upper, has_digit, has_symbol))
    if char_classes < 3 and not (has_lower and has_upper and has_digit):
        return False
    if cleaned.isdigit() or cleaned.isalpha():
        return False

    if _has_sequential_run(cleaned, run_len=6):
        return False
    if _has_repeated_pattern(cleaned):
        return False

    return True


def generate_admin_token(nbytes: int = 32) -> str:
    """Genera una credencial administrativa con CSPRNG (secrets.token_urlsafe(32))."""
    for _ in range(50):
        candidate = secrets.token_urlsafe(max(32, nbytes))
        if is_strong_admin_token(candidate):
            return candidate
    raise RuntimeError("No fue posible generar un ADMIN_TOKEN válido con CSPRNG.")


def validate_admin_token_or_raise(token: str | None = None) -> None:
    effective = settings.ADMIN_TOKEN if token is None else token
    if not is_strong_admin_token(effective):
        raise RuntimeError(
            "Configuración insegura: ADMIN_TOKEN falta o fue rechazado por la política de seguridad "
            "(patrón contextual, de demostración, secuencial o formato inválido). "
            "Genere el secreto localmente con CSPRNG: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
        )


settings = Settings()
