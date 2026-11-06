#!/usr/bin/env bash
set -euo pipefail

echo "================================================================="
echo " CIVIA — Despliegue Autónomo Local (Santiago de Cali / UCC)"
echo "================================================================="

# 1. Comprobación de Docker CLI
if ! command -v docker >/dev/null 2>&1; then
    echo "ERROR: Docker no se encuentra instalado o no está en el PATH del sistema." >&2
    exit 1
fi

# 2. Comprobación de Docker Engine activo
if ! docker info >/dev/null 2>&1; then
    echo "ERROR: El demonio de Docker no está respondiendo. Inicie Docker Desktop o el servicio dockerd." >&2
    exit 1
fi

# 3. Comprobación de Docker Compose
if ! docker compose version >/dev/null 2>&1; then
    echo "ERROR: 'docker compose' no está disponible." >&2
    exit 1
fi

# 4. Generación y protección de .env
IS_FRESH_ENV=0
if [ ! -f .env ]; then
    if [ ! -f .env.example ]; then
        echo "ERROR: No se encontró el archivo '.env.example' como plantilla." >&2
        exit 1
    fi
    cp .env.example .env
    IS_FRESH_ENV=1
    echo "[OK] Archivo de configuración local .env inicializado desde .env.example."
fi

# 5. Generación CSPRNG de ADMIN_TOKEN si no cumple política
if ! grep -qE '^ADMIN_TOKEN=[A-Za-z0-9_-]{32,256}$' .env 2>/dev/null; then
    if command -v openssl >/dev/null 2>&1; then
        GENERATED_TOKEN=$(openssl rand -base64 32 | tr -d '=' | tr '+/' '-_')
    else
        GENERATED_TOKEN=$(head -c 32 /dev/urandom | base64 | tr -d '=' | tr '+/' '-_')
    fi
    if grep -q '^ADMIN_TOKEN=' .env; then
        sed -i.bak -E "s/^ADMIN_TOKEN=.*$/ADMIN_TOKEN=${GENERATED_TOKEN}/" .env && rm -f .env.bak
    else
        echo "ADMIN_TOKEN=${GENERATED_TOKEN}" >> .env
    fi
    echo "[OK] ADMIN_TOKEN robusto y único generado con CSPRNG en .env."
fi

# 6 & 7. Generación de contraseña segura de PostgreSQL para instalación nueva
if [ "$IS_FRESH_ENV" -eq 1 ]; then
    if command -v openssl >/dev/null 2>&1; then
        GEN_PW=$(openssl rand -hex 16)
    else
        GEN_PW=$(head -c 16 /dev/urandom | od -An -tx1 | tr -d ' \n')
    fi
    sed -i.bak -E "s/^POSTGRES_PASSWORD=.*$/POSTGRES_PASSWORD=${GEN_PW}/" .env && rm -f .env.bak
    sed -i.bak -E "s|^DATABASE_URL=.*$|DATABASE_URL=postgresql://civia:${GEN_PW}@db:5432/civia|" .env && rm -f .env.bak
    echo "[OK] Credenciales seguras para PostgreSQL configuradas en .env."
fi

# 8. Despliegue con Docker Compose
echo "Construyendo y levantando contenedores (PostgreSQL 17, FastAPI, Nginx PWA)..."
docker compose up --build -d

# 9. Verificación activa de salud
echo "Verificando disponibilidad de servicios..."
HEALTHY=0
for i in $(seq 1 20); do
    sleep 2
    if curl -s --max-time 3 http://127.0.0.1:8000/health 2>/dev/null | grep -q '"status":"ok"'; then
        if curl -s -I --max-time 3 http://127.0.0.1:5173 2>/dev/null | grep -qE 'HTTP/1\.[01] 200'; then
            HEALTHY=1
            break
        fi
    fi
done

if [ "$HEALTHY" -eq 1 ]; then
    echo "[OK] Todos los servicios se encuentran activos y saludables."
else
    echo "AVISO: Los servicios tardaron en responder. Revise logs con: docker compose logs"
fi

echo "================================================================="
echo " CIVIA DESPLEGADO CON ÉXITO"
echo " - Aplicación Web PWA:   http://localhost:5173"
echo " - API Backend & Docs:   http://localhost:8000/docs"
echo " - Health Check:         http://localhost:8000/health"
echo "================================================================="
