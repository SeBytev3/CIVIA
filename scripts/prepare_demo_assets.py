#!/usr/bin/env python3
"""
CIVIA - Empaquetado y Preparación de Activos Fotográficos Sintéticos Fotorrealistas
Procesa las 10 fotografías generadas con IA, añade la franja de simulación ética y
las almacena en backend/app/demo_assets/ y frontend/public/demo_evidence/.
"""

import hashlib
import os
from pathlib import Path
from PIL import Image, ImageDraw

RAW_DIR = Path(r"C:\Users\Jhoesp\.gemini\antigravity\brain\8366dceb-84e0-44f7-9a1f-795fad86decb")
BACKEND_ASSETS_DIR = Path(r"C:\Users\Jhoesp\Desarrollo\CIVIA\backend\app\demo_assets")
FRONTEND_PUBLIC_DIR = Path(r"C:\Users\Jhoesp\Desarrollo\CIVIA\frontend\public\demo_evidence")

MAPPING = [
    ("CIV-2026-DEMO0001", "HUECO", "cali_urban_pothole_1793915187698.jpg", "Avenida Sexta con Calle 25, Santa Mónica Residencial"),
    ("CIV-2026-DEMO0002", "BASURAS", "cali_garbage_rubble_corner_png_1793915279967.jpg", "Calle 42 con Carrera 46, Mariano Ramos"),
    ("CIV-2026-DEMO0003", "TALA", "saman_talado_pance_1793915283726.jpg", "Vía a Pance km 2.5, Pance"),
    ("CIV-2026-DEMO0004", "QUEMA", "incendio_tres_cruces_cali_1793915299155.jpg", "Sendero Bataclán - Cerro de las Tres Cruces"),
    ("CIV-2026-DEMO0005", "HUECO", "cali_pothole_cracking_1793915312594.jpg", "Calle 5 con Carrera 34, San Fernando Nuevo"),
    ("CIV-2026-DEMO0006", "BASURAS", "cali_escombros_separador_1793915315428.jpg", "Carrera 8 con Calle 73, Alfonso López"),
    ("CIV-2026-DEMO0007", "QUEMA", "quema_lote_baldio_cali_1793915299528.jpg", "Carrera 42B con Calle 50, Ciudad Córdoba"),
    ("CIV-2026-DEMO0008", "TALA", "ramas_bloqueando_anden_cali_1793915301484.jpg", "Calle 10 con Carrera 78, Capri"),
    ("CIV-2026-DEMO0009", "HUECO", "cali_sinkhole_collapse_1793915306505.jpg", "Carrera 1D con Calle 62, Chiminangos"),
    ("CIV-2026-DEMO0010", "BASURAS", "cali_san_pascual_street_waste_png_1793915310607.jpg", "Carrera 15 con Calle 13, San Pascual / El Calvario"),
]

def process_assets():
    BACKEND_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    FRONTEND_PUBLIC_DIR.mkdir(parents=True, exist_ok=True)

    summary_rows = []

    for code, cat, raw_name, location in MAPPING:
        raw_path = RAW_DIR / raw_name
        if not raw_path.exists():
            raise FileNotFoundError(f"No existe el archivo origen: {raw_path}")

        im = Image.open(raw_path).convert("RGB")
        w, h = im.size

        # Agregar banner de identificación ética en franja inferior
        banner_h = 36
        draw = ImageDraw.Draw(im)
        draw.rectangle([0, h - banner_h, w, h], fill=(15, 23, 42))
        watermark_text = f"CIVIA · SIMULACIÓN IA · EVIDENCIA SINTÉTICA DEMO · NO PRIVADO · RADICADO: {code}"
        draw.text((16, h - banner_h + 10), watermark_text, fill=(241, 245, 249))

        dest_backend = BACKEND_ASSETS_DIR / f"{code.lower()}.jpg"
        im.save(dest_backend, "JPEG", quality=88, optimize=True)

        data = dest_backend.read_bytes()
        sha256 = hashlib.sha256(data).hexdigest()
        size_bytes = len(data)

        summary_rows.append({
            "code": code,
            "category": cat,
            "filename": f"{code.lower()}.jpg",
            "dimensions": f"{w}x{h}",
            "size_kb": round(size_bytes / 1024, 1),
            "sha256": sha256,
            "location": location,
        })

    # Generar muestras representativas para frontend/public/demo_evidence
    category_samples = {
        "HUECO": "civ-2026-demo0001.jpg",
        "BASURAS": "civ-2026-demo0002.jpg",
        "TALA": "civ-2026-demo0003.jpg",
        "QUEMA": "civ-2026-demo0004.jpg",
        "OTRO": "civ-2026-demo0009.jpg",
    }
    for cat_name, asset_name in category_samples.items():
        src_path = BACKEND_ASSETS_DIR / asset_name
        dst_path = FRONTEND_PUBLIC_DIR / f"sample_{cat_name.lower()}.jpg"
        dst_path.write_bytes(src_path.read_bytes())

    print("=== RESUMEN DE ACTIVOS FOTOGRÁFICOS SINTÉTICOS PREPARADOS ===")
    for row in summary_rows:
        print(f"{row['code']} | {row['category']:<7} | {row['filename']} | {row['dimensions']} | {row['size_kb']} KB | SHA: {row['sha256'][:16]}... | {row['location']}")

if __name__ == "__main__":
    process_assets()
