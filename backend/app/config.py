import os
from pathlib import Path
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
    AI_TERTIARY_MODEL: str = os.getenv("AI_TERTIARY_MODEL", "gemini-3.6-flash")
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
    "civia-admin-demo",
    "change_me",
    "changeme",
    "password",
    "admin123",
    "replace_with",
    "default_token",
    "example_token",
    "qwerty",
    "asdfgh",
    "zxcvbn",
)

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


def _has_sequential_run(value: str, run_len: int = 5) -> bool:
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


def is_strong_admin_token(token: str | None) -> bool:
    """
    Valida que ADMIN_TOKEN no sea vacío ni coincida con patrones predecibles
    (secuencias numéricas/alfabéticas, repeticiones periódicas, contraseñas de demostración
    o cadenas de una sola clase de caracteres).
    Nota de seguridad: las validaciones deterministas descartan credenciales débiles o de
    demostración; la impredecibilidad real proviene de generar el token con un CSPRNG
    como secrets.token_urlsafe(32).
    """
    if not token or not isinstance(token, str):
        return False
    cleaned = token.strip()
    if len(cleaned) < 24 or len(cleaned) > 256:
        return False
    if any(ch.isspace() for ch in cleaned):
        return False
    if len(set(cleaned)) < 10:
        return False

    low = cleaned.lower()
    if low in WEAK_ADMIN_TOKENS:
        return False
    if any(w in low for w in _WEAK_SUBSTRINGS):
        return False

    has_lower = any("a" <= c <= "z" for c in cleaned)
    has_upper = any("A" <= c <= "Z" for c in cleaned)
    has_digit = any("0" <= c <= "9" for c in cleaned)
    has_symbol = any(not c.isalnum() for c in cleaned)
    char_classes = sum((has_lower, has_upper, has_digit, has_symbol))
    if char_classes < 2:
        return False
    if cleaned.isdigit() or cleaned.isalpha():
        return False

    if _has_sequential_run(cleaned, run_len=5):
        return False
    if _has_repeated_pattern(cleaned):
        return False

    return True


def generate_admin_token(nbytes: int = 32) -> str:
    """Genera una credencial administrativa criptográficamente segura con CSPRNG."""
    for _ in range(20):
        candidate = secrets.token_urlsafe(max(32, nbytes))
        if is_strong_admin_token(candidate):
            return candidate
    return secrets.token_urlsafe(48)


def validate_admin_token_or_raise(token: str | None = None) -> None:
    effective = settings.ADMIN_TOKEN if token is None else token
    if not is_strong_admin_token(effective):
        raise RuntimeError(
            "Configuración insegura: ADMIN_TOKEN falta o presenta un patrón predecible/débil. "
            "Genere un secreto criptográfico con CSPRNG: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
        )


settings = Settings()
