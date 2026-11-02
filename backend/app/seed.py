import hashlib
import io
import json
from pathlib import Path
from typing import Any
from uuid import UUID

from PIL import Image, ImageDraw

from app.config import settings
from app.db import assert_disposable_test_db, get_conn


def generate_synthetic_evidence_png(kind: str, code: str, width: int = 240, height: int = 160) -> bytes:
    """Genera una imagen PNG sintética identificada (>=240x160 px) para pruebas y demo."""
    img = Image.new("RGB", (width, height), color=(235, 238, 242))
    draw = ImageDraw.Draw(img)

    kind_u = kind.upper()
    if kind_u == "HUECO":
        # Asfalto gris con líneas viales y cráter oscuro en la calzada
        draw.rectangle([0, 30, width, height - 24], fill=(82, 86, 92))
        draw.rectangle([15, 92, 55, 98], fill=(245, 208, 66))
        draw.rectangle([185, 92, 225, 98], fill=(245, 208, 66))
        draw.ellipse([70, 58, 170, 125], fill=(28, 30, 34), outline=(140, 140, 145), width=3)
        draw.ellipse([86, 70, 152, 114], fill=(45, 38, 32))
    elif kind_u == "BASURAS":
        # Acera y acumulación de bolsas y residuos sólidos
        draw.rectangle([0, 30, width, 100], fill=(195, 210, 225))
        draw.rectangle([0, 100, width, height - 24], fill=(150, 155, 160))
        draw.ellipse([45, 68, 110, 126], fill=(35, 42, 46))
        draw.ellipse([95, 62, 165, 128], fill=(46, 115, 68))
        draw.ellipse([140, 78, 198, 128], fill=(168, 118, 62))
        draw.rectangle([75, 55, 145, 82], fill=(215, 75, 65))
    elif kind_u == "TALA":
        # Pradera verde con tocón de árbol cortado y tronco caído
        draw.rectangle([0, 30, width, 85], fill=(185, 225, 245))
        draw.rectangle([0, 85, width, height - 24], fill=(88, 158, 82))
        draw.rectangle([50, 75, 92, 122], fill=(118, 76, 42))
        draw.ellipse([48, 68, 94, 84], fill=(212, 175, 125), outline=(92, 58, 28), width=2)
        draw.polygon([(105, 102), (205, 88), (212, 112), (110, 122)], fill=(110, 70, 38))
        draw.ellipse([175, 68, 232, 122], fill=(48, 118, 52))
    elif kind_u == "QUEMA":
        # Ladera con llamas naranjas/rojas y columna de humo gris
        draw.rectangle([0, 30, width, 95], fill=(140, 145, 155))
        draw.polygon([(0, 136), (75, 78), (175, 92), (width, 136)], fill=(96, 82, 65))
        draw.ellipse([85, 32, 185, 86], fill=(95, 98, 105))
        draw.polygon([(70, 122), (98, 56), (124, 122)], fill=(235, 68, 36))
        draw.polygon([(105, 124), (135, 48), (168, 124)], fill=(250, 142, 32))
        draw.polygon([(115, 124), (135, 72), (154, 124)], fill=(255, 215, 55))
    else:
        draw.rectangle([0, 30, width, height - 24], fill=(120, 145, 175))

    # Franja superior e inferior identificando explícitamente que es dato sintético
    draw.rectangle([0, 0, width, 28], fill=(22, 36, 56))
    draw.text((8, 8), f"SINTETICO DEMO CIVIA - {kind_u}", fill=(255, 255, 255))
    draw.rectangle([0, height - 24, width, height], fill=(38, 52, 72))
    draw.text((8, height - 18), f"REF: {code} (NO PRIVADO)", fill=(220, 232, 245))

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

                png_bytes = generate_synthetic_evidence_png(item["ai_category"], item["tracking_code"])
                photo_name = f"synthetic_{item['tracking_code'].lower()}.png"
                (upload_dir / photo_name).write_bytes(png_bytes)
                sha256_hex = hashlib.sha256(png_bytes).hexdigest()

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
                        %s, 'image/png', %s,
                        240, 160, %s,
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
                        len(png_bytes),
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
