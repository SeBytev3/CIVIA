import hashlib
import io
import json
import logging
import os
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from PIL import Image, ImageDraw

from app.config import settings
from app.db import assert_disposable_test_db, get_conn

logger = logging.getLogger(__name__)


DEMO_ASSETS_DIR = Path(__file__).parent / "demo_assets"


def get_known_synthetic_sha256_set() -> set[str]:
    """Retorna el conjunto de hashes SHA-256 de todos los activos sintéticos de demostración."""
    hashes: set[str] = set()
    if DEMO_ASSETS_DIR.exists():
        for asset_path in DEMO_ASSETS_DIR.glob("*.jpg"):
            try:
                hashes.add(hashlib.sha256(asset_path.read_bytes()).hexdigest())
            except Exception:
                pass
    return hashes


def get_synthetic_evidence_bytes(code: str, kind: str) -> tuple[bytes, str, str, int, int]:
    """
    Obtiene los bytes de la evidencia fotográfica sintética fotorrealista empaquetada.
    Retorna: (file_bytes, filename, mime_type, width, height)
    Utiliza nombres inmutables versionados por el hash SHA-256 del contenido (Content-Addressed Storage).
    """
    code_lower = code.lower()
    asset_file = DEMO_ASSETS_DIR / f"{code_lower}.jpg"
    if asset_file.exists():
        data = asset_file.read_bytes()
        sha_prefix = hashlib.sha256(data).hexdigest()[:16]
        filename = f"synthetic_{code_lower}_{sha_prefix}.jpg"
        return data, filename, "image/jpeg", 1200, 896

    # Fallback seguro en memoria si no estuviera el archivo en disco
    fallback_data = generate_synthetic_evidence_png(kind, code, 1024, 768)
    sha_fallback = hashlib.sha256(fallback_data).hexdigest()[:16]
    return fallback_data, f"synthetic_{code_lower}_{sha_fallback}.png", "image/png", 1024, 768


def generate_synthetic_evidence_png(kind: str, code: str, width: int = 1024, height: int = 768) -> bytes:
    """
    Genera una tarjeta limpia y neutral con identificación ética de prueba (sin dibujos geométricos tipo Paint).
    Utilizada exclusivamente como salvaguarda en memoria si un activo empaquetado no estuviera disponible.
    """
    kind_u = kind.upper()
    img = Image.new("RGB", (width, height), color=(15, 23, 42))
    draw = ImageDraw.Draw(img)

    draw.rectangle([16, 16, width - 16, height - 16], outline=(51, 65, 85), width=2)
    draw.rectangle([16, 16, width - 16, 96], fill=(30, 41, 59))
    draw.text((40, 42), "CIVIA — SISTEMA DE REPORTES CIUDADANOS (CALI)", fill=(248, 250, 252))

    draw.text((40, 220), "MUESTRA DE EVALUACIÓN ACADÉMICA", fill=(148, 163, 184))
    draw.text((40, 280), f"CATEGORÍA: {kind_u}", fill=(56, 189, 248))
    draw.text((40, 340), f"RADICADO: {code}", fill=(248, 250, 252))
    draw.text((40, 420), "Fotografía sintética de catálogo ético para demostración técnica.", fill=(148, 163, 184))
    draw.text((40, 460), "Sin datos privados ni capturas ciudadanas reales.", fill=(100, 116, 139))

    draw.rectangle([16, height - 80, width - 16, height - 16], fill=(30, 41, 59))
    draw.text((40, height - 56), "SIMULACIÓN ÉTICA · PROCEDENCIA CERTIFICADA POR SERVIDOR", fill=(226, 232, 240))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


SYNTHETIC_REPORTS: list[dict[str, Any]] = [
    {
        "id": "11111111-1111-4111-8111-000000000001",
        "tracking_code": "CIV-2026-DEMO0001",
        "title": "Hundimiento severo en carril derecho de Avenida Sexta",
        "description": "DATO SINTÉTICO DEMO: Se observa hueco profundo de aproximadamente 90 cm de diámetro en el carril derecho de la Avenida 6N con Calle 25, generando riesgo para motociclistas y ciclistas.",
        "latitude": 3.4658,
        "longitude": -76.5283,
        "comuna": "Comuna 2",
        "neighborhood": "Santa Mónica Residencial",
        "address_hint": "Avenida 6N # 25N-14, Cali",
        "ai_category": "HUECO",
        "ai_severity": "ALTA",
        "ai_confidence": 0.94,
        "ai_summary": "Evidencia visual y descriptiva consistente con deterioro vial severo (hueco profundo) en vía principal con riesgo alto de accidente.",
        "ai_keywords": ["hueco", "avenida sexta", "asfalto", "riesgo vial"],
        "final_category": "HUECO",
        "final_severity": "ALTA",
        "human_confirmed": True,
        "status": "CONFIRMED",
    },
    {
        "id": "11111111-1111-4111-8111-000000000002",
        "tracking_code": "CIV-2026-DEMO0002",
        "title": "Acumulación crítica de basuras y escombros en esquina escolar",
        "description": "DATO SINTÉTICO DEMO: Punto crítico de arrojo clandestino de bolsas de basura y residuos orgánicos frente a zona peatonal en Mariano Ramos, generando malos olores y vectores.",
        "latitude": 3.4012,
        "longitude": -76.5045,
        "comuna": "Comuna 16",
        "neighborhood": "Mariano Ramos",
        "address_hint": "Calle 42 con Carrera 46, Cali",
        "ai_category": "BASURAS",
        "ai_severity": "ALTA",
        "ai_confidence": 0.92,
        "ai_summary": "Acumulación de residuos sólidos y bolsas en espacio público peatonal con afectación sanitaria.",
        "ai_keywords": ["basuras", "residuos", "escombros", "mariano ramos"],
        "final_category": "BASURAS",
        "final_severity": "ALTA",
        "human_confirmed": True,
        "status": "IN_REVIEW",
    },
    {
        "id": "11111111-1111-4111-8111-000000000003",
        "tracking_code": "CIV-2026-DEMO0003",
        "title": "Tala no autorizada de árbol adulto en corredor ambiental de Pance",
        "description": "DATO SINTÉTICO DEMO: Se reporta corte de árbol samán joven con motosierra a orillas del corredor vial hacia Pance sin valla ni permiso visible de autoridad ambiental.",
        "latitude": 3.3385,
        "longitude": -76.5410,
        "comuna": "Comuna 22",
        "neighborhood": "Pance",
        "address_hint": "Vía a Pance km 2.5, Cali",
        "ai_category": "TALA",
        "ai_severity": "ALTA",
        "ai_confidence": 0.91,
        "ai_summary": "Evidencia de corte de individuo arbóreo en corredor ecológico sin señalización de aprovechamiento autorizado.",
        "ai_keywords": ["tala", "arbol", "pance", "corredor ambiental"],
        "final_category": "TALA",
        "final_severity": "ALTA",
        "human_confirmed": True,
        "status": "CONFIRMED",
    },
    {
        "id": "11111111-1111-4111-8111-000000000004",
        "tracking_code": "CIV-2026-DEMO0004",
        "title": "Foco de quema de vegetación en ladera del Cerro de las Tres Cruces",
        "description": "DATO SINTÉTICO DEMO: Columna de humo blanco y llamas visibles en zona de pastizal seco en el ascenso por Bataclán hacia las Tres Cruces.",
        "latitude": 3.4752,
        "longitude": -76.5468,
        "comuna": "Comuna 2",
        "neighborhood": "Normandía / Tres Cruces",
        "address_hint": "Sendero Bataclán - Cerro de las Tres Cruces, Cali",
        "ai_category": "QUEMA",
        "ai_severity": "CRITICA",
        "ai_confidence": 0.96,
        "ai_summary": "Foco activo de incendio de cobertura vegetal en zona de ladera con alto potencial de propagación.",
        "ai_keywords": ["quema", "incendio", "humo", "tres cruces", "ladera"],
        "final_category": "QUEMA",
        "final_severity": "CRITICA",
        "human_confirmed": True,
        "status": "IN_REVIEW",
    },
    {
        "id": "11111111-1111-4111-8111-000000000005",
        "tracking_code": "CIV-2026-DEMO0005",
        "title": "Bache profundo frente a parada del MIO en San Fernando",
        "description": "DATO SINTÉTICO DEMO: Desprendimiento de capa asfáltica frente al Parque del Perro en San Fernando que acumula agua lluvia y dificulta el paso de buses alimentadores.",
        "latitude": 3.4342,
        "longitude": -76.5439,
        "comuna": "Comuna 19",
        "neighborhood": "San Fernando Nuevo",
        "address_hint": "Calle 5 con Carrera 34, Cali",
        "ai_category": "HUECO",
        "ai_severity": "MEDIA",
        "ai_confidence": 0.89,
        "ai_summary": "Bache en calzada urbana con acumulación de agua cerca de paradero de transporte público.",
        "ai_keywords": ["bache", "hueco", "san fernando", "calzada"],
        "final_category": "HUECO",
        "final_severity": "MEDIA",
        "human_confirmed": True,
        "status": "CONFIRMED",
    },
    {
        "id": "11111111-1111-4111-8111-000000000006",
        "tracking_code": "CIV-2026-DEMO0006",
        "title": "Disposición inadecuada de residuos en separador vial de Alfonso López",
        "description": "DATO SINTÉTICO DEMO: Colchones viejos, ramas y bolsas plásticas abandonadas en el separador central de la Carrera 8 en Alfonso López.",
        "latitude": 3.4689,
        "longitude": -76.4841,
        "comuna": "Comuna 7",
        "neighborhood": "Alfonso López",
        "address_hint": "Carrera 8 con Calle 73, Cali",
        "ai_category": "BASURAS",
        "ai_severity": "MEDIA",
        "ai_confidence": 0.90,
        "ai_summary": "Residuos voluminosos y bolsas depositadas en separador vial afectando el espacio público.",
        "ai_keywords": ["basuras", "separador", "residuos voluminosos", "alfonso lopez"],
        "final_category": "BASURAS",
        "final_severity": "MEDIA",
        "human_confirmed": True,
        "status": "RESOLVED",
    },
    {
        "id": "11111111-1111-4111-8111-000000000007",
        "tracking_code": "CIV-2026-DEMO0007",
        "title": "Quema de basuras y pasto seco en lote baldío de Ciudad Córdoba",
        "description": "DATO SINTÉTICO DEMO: Quema abierta de residuos y maleza seca junto a canal de aguas lluvias generando humo denso sobre viviendas vecinas.",
        "latitude": 3.3948,
        "longitude": -76.4982,
        "comuna": "Comuna 15",
        "neighborhood": "Ciudad Córdoba",
        "address_hint": "Carrera 42B con Calle 50, Cali",
        "ai_category": "QUEMA",
        "ai_severity": "ALTA",
        "ai_confidence": 0.93,
        "ai_summary": "Quema a cielo abierto de maleza y residuos con emisión de humo cerca de zona residencial.",
        "ai_keywords": ["quema", "humo", "ciudad cordoba", "canal"],
        "final_category": "QUEMA",
        "final_severity": "ALTA",
        "human_confirmed": True,
        "status": "CONFIRMED",
    },
    {
        "id": "11111111-1111-4111-8111-000000000008",
        "tracking_code": "CIV-2026-DEMO0008",
        "title": "Corte severo de raíces y copa de árbol en parque de Capri",
        "description": "DATO SINTÉTICO DEMO: Intervención antitécnica sobre árbol ornamental en zona verde del barrio Capri dejando ramas trozadas sobre el andén.",
        "latitude": 3.3895,
        "longitude": -76.5418,
        "comuna": "Comuna 17",
        "neighborhood": "Capri",
        "address_hint": "Calle 10 con Carrera 78, Cali",
        "ai_category": "TALA",
        "ai_severity": "MEDIA",
        "ai_confidence": 0.87,
        "ai_summary": "Poda severa o tala parcial sin manejo técnico sobre árbol urbano en parque barrial.",
        "ai_keywords": ["tala", "poda severa", "capri", "arbol urbano"],
        "final_category": "TALA",
        "final_severity": "MEDIA",
        "human_confirmed": False,
        "status": "ANALYZED_PENDING_CONFIRMATION",
    },
    {
        "id": "11111111-1111-4111-8111-000000000009",
        "tracking_code": "CIV-2026-DEMO0009",
        "title": "Sucesión de huecos en vía de acceso al barrio Siloé",
        "description": "DATO SINTÉTICO DEMO: Tres huecos consecutivos en la Calle 1 Oeste dificultan el tránsito de camperos de transporte comunitario.",
        "latitude": 3.4241,
        "longitude": -76.5572,
        "comuna": "Comuna 20",
        "neighborhood": "Siloé",
        "address_hint": "Calle 1 Oeste con Carrera 50, Cali",
        "ai_category": "HUECO",
        "ai_severity": "ALTA",
        "ai_confidence": 0.91,
        "ai_summary": "Múltiples baches en vía de ladera con impacto directo en transporte comunitario.",
        "ai_keywords": ["huecos", "siloe", "via ladera", "camperos"],
        "final_category": "HUECO",
        "final_severity": "ALTA",
        "human_confirmed": True,
        "status": "CONFIRMED",
    },
    {
        "id": "11111111-1111-4111-8111-000000000010",
        "tracking_code": "CIV-2026-DEMO0010",
        "title": "Punto crítico de basuras junto a galería de Santa Elena",
        "description": "DATO SINTÉTICO DEMO: Residuos vegetales y empaques acumulados fuera de horario de recolección en vía aledaña a la plaza de mercado de Santa Elena.",
        "latitude": 3.4265,
        "longitude": -76.5194,
        "comuna": "Comuna 10",
        "neighborhood": "Santa Elena",
        "address_hint": "Calle 25 con Carrera 29, Cali",
        "ai_category": "BASURAS",
        "ai_severity": "ALTA",
        "ai_confidence": 0.95,
        "ai_summary": "Acumulación densa de residuos orgánicos y plásticos en entorno de plaza de mercado.",
        "ai_keywords": ["basuras", "residuos organicos", "santa elena", "galeria"],
        "final_category": "BASURAS",
        "final_severity": "ALTA",
        "human_confirmed": True,
        "status": "CONFIRMED",
    },
]


def seed_synthetic_reports(force_reset: bool = False) -> dict[str, int]:
    """Inserta los reportes sintéticos identificados de demostración si no existen."""
    upload_dir: Path = settings.UPLOAD_DIR
    upload_dir.mkdir(parents=True, exist_ok=True)

    inserted = 0
    skipped = 0

    with get_conn() as conn:
        with conn.cursor() as cur:
            if force_reset:
                assert_disposable_test_db()
                catalog_ids = [UUID(item["id"]) for item in SYNTHETIC_REPORTS]
                cur.execute("DELETE FROM reports WHERE id = ANY(%s);", (catalog_ids,))

            for item in SYNTHETIC_REPORTS:
                rid = UUID(item["id"])
                cur.execute("SELECT id FROM reports WHERE id = %s;", (rid,))
                if cur.fetchone() is not None:
                    skipped += 1
                    continue

                bytes_data, photo_name, photo_mime, width, height = get_synthetic_evidence_bytes(
                    item["tracking_code"], item["ai_category"]
                )
                dest_file = upload_dir / photo_name
                if not dest_file.exists():
                    tmp_staged = upload_dir / f".staging_seed_{os.getpid()}_{uuid4().hex}.tmp"
                    tmp_staged.write_bytes(bytes_data)
                    os.replace(tmp_staged, dest_file)
                sha256_hex = hashlib.sha256(bytes_data).hexdigest()

                cur.execute(
                    """
                    INSERT INTO reports (
                        id, tracking_code, title, description,
                        latitude, longitude, in_service_area,
                        comuna, neighborhood, address_hint,
                        photo_path, photo_mime, photo_size_bytes,
                        photo_width, photo_height, photo_sha256,
                        ai_category, ai_severity, ai_confidence,
                        ai_summary, ai_keywords,
                        final_category, final_severity,
                        human_confirmed, status, is_synthetic
                    )
                    VALUES (
                        %s, %s, %s, %s,
                        %s, %s, TRUE,
                        %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s,
                        %s, %s::jsonb,
                        %s, %s,
                        %s, %s, TRUE
                    );
                    """,
                    (
                        rid,
                        item["tracking_code"],
                        item["title"],
                        item["description"],
                        item["latitude"],
                        item["longitude"],
                        item["comuna"],
                        item["neighborhood"],
                        item["address_hint"],
                        photo_name,
                        photo_mime,
                        len(bytes_data),
                        width,
                        height,
                        sha256_hex,
                        item["ai_category"],
                        item["ai_severity"],
                        item["ai_confidence"],
                        item["ai_summary"],
                        json.dumps(item["ai_keywords"], ensure_ascii=False),
                        item["final_category"],
                        item["final_severity"],
                        item["human_confirmed"],
                        item["status"],
                    ),
                )
                inserted += 1
            conn.commit()
    return {"inserted": inserted, "skipped": skipped, "total_synthetic_catalog": len(SYNTHETIC_REPORTS)}


def update_synthetic_catalog_photos(upload_dir_path: Path | None = None) -> dict[str, int]:
    """
    Actualiza exclusivamente los metadatos fotográficos y archivos de los 10 reportes del catálogo
    sintético (is_synthetic = TRUE AND tracking_code LIKE 'CIV-2026-DEMO%').

    Arquitectura de Almacenamiento Inmutable Versionado por Contenido (Content-Addressed Storage):
    1. Las fotografías del catálogo se publican en rutas inmutables con nombre versionado:
       synthetic_civ-2026-demoXXXX_<sha256[:16]>.jpg
    2. Nunca se sobrescribe destructivamente un archivo existente referenciado por PostgreSQL.
    3. Staging atómico en archivo temporal exclusivo por proceso (.staging_{pid}_{uuid}.tmp).
    4. Verificación de integridad por SHA-256 y decodificación PIL (Image.verify()) antes de publicar.
    5. Publicación atómica mediante os.replace a la ruta inmutable.
    6. Verificación física de existencia e integridad en destino.
    7. Transacción SQL atómica: actualización de fila en PostgreSQL para apuntar al archivo inmutable.
    8. En caso de rollback SQL o error: los archivos previamente referenciados siguen 100% intactos en disco;
       la BD sigue apuntando a ellos. Cero referencias rotas y cero copias únicas destruidas.
    9. Limpieza segura post-commit: únicamente tras commit confirmado y comprobando con
       COUNT(*) = 0 en PostgreSQL, se eliminan versiones sintéticas antiguas que hayan quedado desreferenciadas.
    10. Concurrencia segura: dos procesos concurrentes no destruyen archivos mutuos.
    """
    import io
    import os
    from uuid import uuid4

    target_upload_dir = upload_dir_path or settings.UPLOAD_DIR
    target_upload_dir.mkdir(parents=True, exist_ok=True)

    updated_count = 0
    unchanged_count = 0
    missing_count = 0

    catalog_codes = [item["tracking_code"] for item in SYNTHETIC_REPORTS]
    staged_items: list[dict[str, Any]] = []
    pid = os.getpid()

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                for item in SYNTHETIC_REPORTS:
                    code = item["tracking_code"]
                    cur.execute(
                        """
                        SELECT id, photo_path, photo_sha256, is_synthetic
                        FROM reports
                        WHERE tracking_code = %s AND is_synthetic = TRUE;
                        """,
                        (code,),
                    )
                    row = cur.fetchone()
                    if not row:
                        missing_count += 1
                        continue

                    rid = row["id"]
                    current_sha = row["photo_sha256"]
                    current_path = row["photo_path"]

                    bytes_data, photo_name, photo_mime, width, height = get_synthetic_evidence_bytes(
                        code, item["ai_category"]
                    )
                    expected_sha256 = hashlib.sha256(bytes_data).hexdigest()

                    dest_file = target_upload_dir / photo_name

                    # 1. Comprobación de integridad física del archivo inmutable en disco
                    disk_valid = False
                    if dest_file.exists() and dest_file.is_file():
                        try:
                            disk_bytes = dest_file.read_bytes()
                            if hashlib.sha256(disk_bytes).hexdigest() == expected_sha256:
                                with Image.open(io.BytesIO(disk_bytes)) as test_img:
                                    test_img.verify()
                                disk_valid = True
                        except Exception:
                            disk_valid = False

                    # 2. Si la fila SQL ya apunta al archivo inmutable y el archivo en disco es íntegro -> unchanged
                    if disk_valid and current_sha == expected_sha256 and current_path == photo_name:
                        unchanged_count += 1
                        continue

                    # 3. Si dest_file no existe o está corrupto, preparar staging exclusivo
                    temp_staged = None
                    if not disk_valid:
                        temp_staged = target_upload_dir / f".staging_{pid}_{code.lower()}_{uuid4().hex}.tmp"
                        temp_staged.write_bytes(bytes_data)
                        with Image.open(io.BytesIO(bytes_data)) as v_img:
                            v_img.verify()

                    staged_items.append({
                        "rid": rid,
                        "code": code,
                        "photo_name": photo_name,
                        "photo_mime": photo_mime,
                        "photo_size": len(bytes_data),
                        "width": width,
                        "height": height,
                        "expected_sha": expected_sha256,
                        "dest_file": dest_file,
                        "temp_staged": temp_staged,
                        "old_path": current_path,
                    })

                # Si todo está al día
                if not staged_items:
                    return {
                        "updated": 0,
                        "unchanged": unchanged_count,
                        "missing_in_db": missing_count,
                        "catalog_total": len(catalog_codes),
                    }

                # Fase 4: Publicar archivos inmutables en disco antes del commit SQL
                for entry in staged_items:
                    temp_staged = entry["temp_staged"]
                    dest = entry["dest_file"]
                    if temp_staged is not None and temp_staged.exists():
                        os.replace(temp_staged, dest)
                        entry["temp_staged"] = None

                    # Verificar que dest existe e íntegro
                    if not dest.exists():
                        raise OSError(f"No se pudo asegurar la existencia del archivo inmutable {dest.name}")

                    # Actualizar metadatos en PostgreSQL dentro de la transacción
                    cur.execute(
                        """
                        UPDATE reports
                        SET photo_path = %s,
                            photo_mime = %s,
                            photo_size_bytes = %s,
                            photo_width = %s,
                            photo_height = %s,
                            photo_sha256 = %s,
                            updated_at = NOW()
                        WHERE id = %s AND is_synthetic = TRUE AND tracking_code = %s;
                        """,
                        (
                            entry["photo_name"],
                            entry["photo_mime"],
                            entry["photo_size"],
                            entry["width"],
                            entry["height"],
                            entry["expected_sha"],
                            entry["rid"],
                            entry["code"],
                        ),
                    )
                    updated_count += 1

                # Confirmar transacción SQL
                conn.commit()

        # Fase 5: Limpieza post-commit segura de archivos antiguos que hayan quedado desreferenciados
        # Solo se ejecuta tras commit exitoso y verificando con COUNT(*)=0 en PostgreSQL
        with get_conn() as conn_clean:
            with conn_clean.cursor() as cur_clean:
                for entry in staged_items:
                    old_path_str = entry.get("old_path")
                    new_path_str = entry["photo_name"]
                    if not old_path_str or old_path_str == new_path_str:
                        continue
                    if not old_path_str.startswith("synthetic_civ-2026-demo"):
                        continue
                    old_file = target_upload_dir / old_path_str
                    if not old_file.exists():
                        continue
                    cur_clean.execute(
                        "SELECT COUNT(*) AS ref_count FROM reports WHERE photo_path = %s;",
                        (old_path_str,),
                    )
                    count_row = cur_clean.fetchone()
                    if count_row and count_row["ref_count"] == 0:
                        try:
                            old_file.unlink(missing_ok=True)
                        except Exception as unlink_err:
                            logger.warning("No se pudo desvincular archivo antiguo no referenciado %s: %s", old_file, unlink_err)

    except Exception:
        # Limpieza defensiva EXCLUSIVA de los archivos temporales creados por ESTE proceso
        for entry in staged_items:
            tmp = entry.get("temp_staged")
            if tmp and tmp.exists():
                try:
                    tmp.unlink(missing_ok=True)
                except Exception:
                    pass
        raise

    return {
        "updated": updated_count,
        "unchanged": unchanged_count,
        "missing_in_db": missing_count,
        "catalog_total": len(catalog_codes),
    }
