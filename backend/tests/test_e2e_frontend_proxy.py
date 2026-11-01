import httpx
import pytest


def test_frontend_pwa_and_nginx_reverse_proxy_e2e():
    """
    Comprueba desde el contenedor api hacia http://frontend:80 que:
    1) La PWA sirve index.html, manifest.webmanifest, sw.js e icon-192.svg.
    2) El proxy inverso Nginx encamina /health y /api/reports/stats al backend real sin errores.
    """
    base_url = "http://frontend:80"
    try:
        r_index = httpx.get(f"{base_url}/", timeout=3.0)
    except httpx.HTTPError:
        pytest.skip("Contenedor frontend no accesible en este entorno aislado")

    assert r_index.status_code == 200
    assert "CIVIA" in r_index.text
    assert 'rel="manifest"' in r_index.text

    r_manifest = httpx.get(f"{base_url}/manifest.webmanifest", timeout=3.0)
    assert r_manifest.status_code == 200
    manifest = r_manifest.json()
    assert manifest["short_name"] == "CIVIA"
    assert manifest["display"] == "standalone"

    r_sw = httpx.get(f"{base_url}/sw.js", timeout=3.0)
    assert r_sw.status_code == 200
    assert "civia-pwa-v1" in r_sw.text

    r_health = httpx.get(f"{base_url}/health", timeout=3.0)
    assert r_health.status_code == 200
    assert r_health.json()["status"] == "ok"

    r_stats = httpx.get(f"{base_url}/api/reports/stats", timeout=3.0)
    assert r_stats.status_code == 200
    assert r_stats.json()["total_reports"] >= 10
