#!/usr/bin/env python3
"""
CIVIA - Empaquetado y Preparación de Activos Fotográficos Sintéticos Fotorrealistas
Procesa las fotografías generadas con IA, añade la franja de simulación ética indeleble,
neutraliza identificadores accidentales y las almacena en backend/app/demo_assets/ y
frontend/public/demo_evidence/.
"""

import hashlib
import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

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

OTRO_RAW = "cali_utility_pole_cables_otro_1793923073433.jpg"

def draw_ethical_banner(im: Image.Image, text: str, banner_h: int = 44) -> Image.Image:
    """Incrusta franja ética indeleble en la base de la imagen con tipografía nítida ASCII."""
    w, h = im.size
    draw = ImageDraw.Draw(im)
    draw.rectangle([0, h - banner_h, w, h], fill=(15, 23, 42))
    draw.line([(0, h - banner_h), (w, h - banner_h)], fill=(51, 65, 85), width=2)
    draw.text((18, h - banner_h + 14), text, fill=(241, 245, 249))
    return im

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

        # Neutralizaciones visuales preventivas de identificadores accidentales
        if code == "CIV-2026-DEMO0001":
            taxi_box = (int(w * 0.70), int(h * 0.38), int(w * 0.88), int(h * 0.52))
            taxi_crop = im.crop(taxi_box).filter(ImageFilter.GaussianBlur(radius=5))
            im.paste(taxi_crop, taxi_box)
        elif code == "CIV-2026-DEMO0010":
            sign_box = (int(w * 0.20), int(h * 0.15), int(w * 0.70), int(h * 0.38))
            sign_crop = im.crop(sign_box).filter(ImageFilter.GaussianBlur(radius=6))
            im.paste(sign_crop, sign_box)

        banner_text = f"CIVIA - SIMULACION IA - EVIDENCIA SINTETICA DEMO - NO PRIVADO - RADICADO: {code}"
        im = draw_ethical_banner(im, banner_text)

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

    # Preparar muestra dedicada e independiente para categoría OTRO
    otro_raw_path = RAW_DIR / OTRO_RAW
    if not otro_raw_path.exists():
        raise FileNotFoundError(f"No existe imagen para categoría OTRO: {otro_raw_path}")

    im_otro = Image.open(otro_raw_path).convert("RGB")
    im_otro = draw_ethical_banner(
        im_otro,
        "CIVIA - SIMULACION IA - EVIDENCIA SINTETICA DEMO - NO PRIVADO - CATEGORIA: OTRO"
    )
    dest_otro_backend = BACKEND_ASSETS_DIR / "sample_otro.jpg"
    im_otro.save(dest_otro_backend, "JPEG", quality=88, optimize=True)
    dst_otro_frontend = FRONTEND_PUBLIC_DIR / "sample_otro.jpg"
    dst_otro_frontend.write_bytes(dest_otro_backend.read_bytes())

    # Generar muestras representativas por categoría para frontend/public/demo_evidence
    category_samples = {
        "HUECO": "civ-2026-demo0001.jpg",
        "BASURAS": "civ-2026-demo0002.jpg",
        "TALA": "civ-2026-demo0003.jpg",
        "QUEMA": "civ-2026-demo0004.jpg",
    }
    for cat_name, asset_name in category_samples.items():
        src_path = BACKEND_ASSETS_DIR / asset_name
        dst_path = FRONTEND_PUBLIC_DIR / f"sample_{cat_name.lower()}.jpg"
        dst_path.write_bytes(src_path.read_bytes())

    print("=== RESUMEN DE ACTIVOS FOTOGRÁFICOS SINTÉTICOS PREPARADOS ===")
    for row in summary_rows:
        print(f"{row['code']} | {row['category']:<7} | {row['filename']} | {row['dimensions']} | {row['size_kb']} KB | SHA: {row['sha256'][:16]}... | {row['location']}")

    otro_data = dst_otro_frontend.read_bytes()
    print(f"SAMPLE_OTRO       | OTRO    | sample_otro.jpg       | {im_otro.size[0]}x{im_otro.size[1]} | {round(len(otro_data)/1024, 1)} KB | SHA: {hashlib.sha256(otro_data).hexdigest()[:16]}... | Cableado y poste ladeado")

if __name__ == "__main__":
    process_assets()
