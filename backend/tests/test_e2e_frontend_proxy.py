import httpx
import pytest


def test_frontend_pwa_and_nginx_reverse_proxy_e2e():
    """
    Comprueba desde el contenedor api hacia http://frontend:80 que:
    1) El portal administrativo sirve su manifiesto y service worker bajo /admin/.
    2) El proxy Nginx publica salud y mapa sanitizado y exige sesión para reportes privados.
    """
    base_url = "http://frontend:80"
    try:
        r_index = httpx.get(f"{base_url}/admin/", timeout=3.0)
    except httpx.HTTPError:
        pytest.skip("Contenedor frontend no accesible en este entorno aislado")

    assert r_index.status_code == 200
    assert "CIVIA" in r_index.text
    assert 'rel="manifest"' in r_index.text

    r_manifest = httpx.get(f"{base_url}/admin/manifest.webmanifest", timeout=3.0)
    assert r_manifest.status_code == 200
    manifest = r_manifest.json()
    assert manifest["short_name"] == "CIVIA Admin"
    assert manifest["display"] == "standalone"
    assert manifest["scope"] == manifest["start_url"] == "/admin/"

    r_sw = httpx.get(f"{base_url}/admin/sw.js", timeout=3.0)
    assert r_sw.status_code == 200
    assert "civia-admin-offline-" in r_sw.text
    assert httpx.get(f"{base_url}/manifest.webmanifest", timeout=3.0).status_code == 410

    r_health = httpx.get(f"{base_url}/health", timeout=3.0)
    assert r_health.status_code == 200
    assert r_health.json()["status"] == "ok"

    r_stats = httpx.get(f"{base_url}/api/public/reports/stats", timeout=3.0)
    assert r_stats.status_code == 200
    assert r_stats.json()["total"] >= 0
    assert httpx.get(f"{base_url}/api/reports/stats", timeout=3.0).status_code == 401
