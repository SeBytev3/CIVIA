import os
from pathlib import Path


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

    # Token de administración para observabilidad protegida y operaciones admin (sin valor por defecto débil)
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


def is_strong_admin_token(token: str | None) -> bool:
    if not token or not isinstance(token, str):
        return False
    cleaned = token.strip()
    if len(cleaned) < 24:
        return False
    if len(set(cleaned)) < 8:
        return False
    low = cleaned.lower()
    if low in WEAK_ADMIN_TOKENS:
        return False
    if "civia-admin-demo" in low or "change_me" in low:
        return False
    return True


def validate_admin_token_or_raise(token: str | None = None) -> None:
    effective = settings.ADMIN_TOKEN if token is None else token
    if not is_strong_admin_token(effective):
        raise RuntimeError(
            "Configuración insegura: ADMIN_TOKEN falta o es débil. "
            "Configure un secreto robusto (>=24 caracteres y alta entropía) generado por instalación."
        )


settings = Settings()
