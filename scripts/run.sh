#!/usr/bin/env bash
# CIVIA — Script de Arranque y Despliegue Autónomo (Linux / macOS)
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

# 7b. Detección y solicitud opcional de credenciales de IA
KEY_PRIMARY=$(grep -E '^GOOGLE_API_KEY_PRIMARY=' .env 2>/dev/null | cut -d'=' -f2- | tr -d '\r' || true)
KEY_SECONDARY=$(grep -E '^GOOGLE_API_KEY_SECONDARY=' .env 2>/dev/null | cut -d'=' -f2- | tr -d '\r' || true)
KEY_GROQ=$(grep -E '^GROQ_API_KEY=' .env 2>/dev/null | cut -d'=' -f2- | tr -d '\r' || true)

update_key_var() {
    local name="$1"
    local val="$2"
    if grep -q "^${name}=" .env; then
        sed -i.bak -E "s|^${name}=.*$|${name}=${val}|" .env && rm -f .env.bak
    else
        echo "${name}=${val}" >> .env
    fi
}

if [ -t 0 ] && [ "${CI:-}" != "true" ] && { [ -z "$KEY_PRIMARY" ] || [ -z "$KEY_SECONDARY" ] || [ -z "$KEY_GROQ" ]; }; then
    echo ""
    echo "[AVISO] Credenciales de IA externas pendientes en .env."
    echo "CIVIA opera plenamente en Modo MVP Local sin claves externas (alta, foto, GPS, mapa y catálogo sintético)."
    read -r -p "¿Desea configurar ahora las claves de Google AI Studio / Groq? (s/N): " ASK_KEYS
    if [ "$ASK_KEYS" = "s" ] || [ "$ASK_KEYS" = "S" ]; then
        if [ -z "$KEY_PRIMARY" ]; then
            read -r -s -p "Google AI Studio Primaria (gemini-3.8-flash) [entrada oculta, Enter para omitir]: " IN_P
            echo ""
            if [ -n "$IN_P" ]; then
                update_key_var "GOOGLE_API_KEY_PRIMARY" "$IN_P"
                KEY_PRIMARY="$IN_P"
            fi
        fi
        if [ -z "$KEY_SECONDARY" ]; then
            read -r -s -p "Google AI Studio Secundaria (gemini-3.5-flash-lite) [entrada oculta, Enter para omitir]: " IN_S
            echo ""
            if [ -n "$IN_S" ]; then
                update_key_var "GOOGLE_API_KEY_SECONDARY" "$IN_S"
                KEY_SECONDARY="$IN_S"
            fi
        fi
        if [ -z "$KEY_GROQ" ]; then
            read -r -s -p "Groq Cloud Fallback (qwen/qwen3.8-27b) [entrada oculta, Enter para omitir]: " IN_G
            echo ""
            if [ -n "$IN_G" ]; then
                update_key_var "GROQ_API_KEY" "$IN_G"
                KEY_GROQ="$IN_G"
            fi
        fi
    fi
elif [ -z "$KEY_PRIMARY" ] || [ -z "$KEY_GROQ" ]; then
    echo "[INFO] Claves de IA no provistas. CIVIA iniciará en Modo MVP Local (sin inferencia remota)."
    echo "       Para configurarlas luego sin reiniciar la base de datos: ./scripts/setup_ai_keys.sh"
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
    echo "[OK] Servicios base activos y saludables."
else
    echo "AVISO: Los servicios tardaron en responder. Revise logs con: docker compose logs"
fi

# 10. Comprobación de estado de proveedores de IA
STATUS_PRIMARY="PENDIENTE"
STATUS_SECONDARY="PENDIENTE"
STATUS_GROQ="PENDIENTE"

AI_JSON=$(docker compose exec -T api python3 -m app.validate_providers --json 2>/dev/null || true)
if [ -n "$AI_JSON" ]; then
    STATUS_PRIMARY=$(echo "$AI_JSON" | grep -o '"google_primary": *{[^}]*}' | grep -o '"status": *"[^"]*"' | cut -d'"' -f4 || echo "PENDIENTE")
    STATUS_SECONDARY=$(echo "$AI_JSON" | grep -o '"google_secondary": *{[^}]*}' | grep -o '"status": *"[^"]*"' | cut -d'"' -f4 || echo "PENDIENTE")
    STATUS_GROQ=$(echo "$AI_JSON" | grep -o '"groq": *{[^}]*}' | grep -o '"status": *"[^"]*"' | cut -d'"' -f4 || echo "PENDIENTE")
fi

echo ""
echo "================================================================="
echo " RESULTADO OBLIGATORIO DEL ARRANQUE — CIVIA"
echo "================================================================="
if [ "$HEALTHY" -eq 1 ]; then
    echo " - Frontend PWA:             DISPONIBLE (http://localhost:5173)"
    echo " - PostgreSQL 17:            CONECTADO (Esquema listo)"
    echo " - API REST & Swagger:       SALUDABLE (http://localhost:8000/docs)"
else
    echo " - Frontend PWA:             FALLIDO"
    echo " - PostgreSQL 17:            FALLIDO"
    echo " - API REST & Swagger:       FALLIDA"
fi
echo " - Google IA primaria:       $STATUS_PRIMARY"
echo " - Google IA secundaria:     $STATUS_SECONDARY"
echo " - Groq Cloud:               $STATUS_GROQ"

if [ "$STATUS_PRIMARY" = "PENDIENTE" ] && [ "$STATUS_GROQ" = "PENDIENTE" ]; then
    echo ""
    echo " [MODO MVP LOCAL ACTIVO]: Inferencia remota en vivo pendiente de claves."
    echo " El sistema opera 100% en modo local (alta de reportes, foto, mapa, GPS y catálogo sintético)."
    echo " Para configurar credenciales en cualquier momento sin tocar la base de datos:"
    echo "   ./scripts/setup_ai_keys.sh"
fi

echo ""
echo "================================================================="
echo " INSTRUCCIONES DE ACCESO ADMINISTRATIVO"
echo "================================================================="
echo " 1. Abra CIVIA en su navegador: http://localhost:5173"
echo " 2. Ingrese a la pestaña 'Administración'."
echo " 3. La clave administrativa fue generada y guardada de forma segura en .env."
echo " 4. Para copiarla al portapapeles sin mostrarla en pantalla ni logs, ejecute:"
echo "    grep '^ADMIN_TOKEN=' .env | cut -d'=' -f2- | tr -d '\\r\\n' | (pbcopy 2>/dev/null || xclip -selection clipboard 2>/dev/null || wl-copy 2>/dev/null || echo \"[Copie la línea ADMIN_TOKEN de .env]\")"
echo "================================================================="
