#!/usr/bin/env bash
# CIVIA — Script de Configuración Segura de Claves de IA (Linux / macOS)
set -euo pipefail

VALIDATE_LIVE=0
NON_INTERACTIVE=0

for arg in "$@"; do
    case "$arg" in
        --live)
            VALIDATE_LIVE=1
            ;;
        --non-interactive)
            NON_INTERACTIVE=1
            ;;
    esac
done

echo "================================================================="
echo " CIVIA — Configuración Segura de Credenciales de IA"
echo "================================================================="

if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        cp .env.example .env
        echo "[OK] .env inicializado desde .env.example."
    else
        echo "ERROR: No se encontró .env ni .env.example en la raíz del repositorio." >&2
        exit 1
    fi
fi

CURRENT_PRIMARY=$(grep -E '^GOOGLE_API_KEY_PRIMARY=' .env 2>/dev/null | cut -d'=' -f2- | tr -d '\r' || true)
CURRENT_SECONDARY=$(grep -E '^GOOGLE_API_KEY_SECONDARY=' .env 2>/dev/null | cut -d'=' -f2- | tr -d '\r' || true)
CURRENT_GROQ=$(grep -E '^GROQ_API_KEY=' .env 2>/dev/null | cut -d'=' -f2- | tr -d '\r' || true)

IS_INTERACTIVE=0
if [ "$NON_INTERACTIVE" -eq 0 ] && [ -t 0 ]; then
    IS_INTERACTIVE=1
fi

prompt_key() {
    local provider_name="$1"
    local current_val="$2"
    local env_override="${3:-}"
    
    if [ -n "$env_override" ]; then
        echo "$env_override"
        return
    fi
    
    if [ "$IS_INTERACTIVE" -eq 0 ]; then
        echo "$current_val"
        return
    fi
    
    if [ -n "$current_val" ]; then
        echo "[$provider_name] Ya configurada en .env." >&2
        read -r -p "¿Desea reemplazarla? (s/N): " replace_choice
        if [ "$replace_choice" != "s" ] && [ "$replace_choice" != "S" ]; then
            echo "$current_val"
            return
        fi
    fi
    
    read -r -s -p "Ingrese la clave para $provider_name (entrada oculta, Enter para omitir): " input_val
    echo "" >&2
    if [ -z "$input_val" ]; then
        echo "$current_val"
    else
        echo "$input_val"
    fi
}

NEW_PRIMARY=$(prompt_key "Google AI Studio (Primaria - gemini-3.8-flash)" "$CURRENT_PRIMARY" "${GOOGLE_API_KEY_PRIMARY:-}")
NEW_SECONDARY=$(prompt_key "Google AI Studio (Secundaria - gemini-3.5-flash-lite)" "$CURRENT_SECONDARY" "${GOOGLE_API_KEY_SECONDARY:-}")
NEW_GROQ=$(prompt_key "Groq Cloud (Fallback - qwen/qwen3.8-27b)" "$CURRENT_GROQ" "${GROQ_API_KEY:-}")

update_env_var() {
    local var_name="$1"
    local var_val="$2"
    if grep -q "^${var_name}=" .env; then
        sed -i.bak -E "s|^${var_name}=.*$|${var_name}=${var_val}|" .env && rm -f .env.bak
    else
        echo "${var_name}=${var_val}" >> .env
    fi
}

update_env_var "GOOGLE_API_KEY_PRIMARY" "$NEW_PRIMARY"
update_env_var "GOOGLE_API_KEY_SECONDARY" "$NEW_SECONDARY"
update_env_var "GROQ_API_KEY" "$NEW_GROQ"

echo "[OK] Archivo .env local actualizado de forma protegida (excluido de Git)."

echo "Recargando variables en el contenedor de API (sin tocar base de datos)..."
docker compose up -d --no-deps api

sleep 2
echo "Verificando variables dentro del contenedor api:"
if [ "$VALIDATE_LIVE" -eq 1 ]; then
    docker compose exec -T api python3 -m app.validate_providers --live
else
    docker compose exec -T api python3 -m app.validate_providers
fi

echo ""
echo "================================================================="
echo " INSTRUCCIONES DE ACCESO ADMINISTRATIVO"
echo " 1. Abra CIVIA en su navegador: http://localhost:5173"
echo " 2. Ingrese a la pestaña 'Administración'."
echo " 3. El ADMIN_TOKEN generado reside en su archivo .env local."
echo " 4. Para copiarlo al portapapeles sin mostrarlo en pantalla ni logs, ejecute:"
echo "    grep '^ADMIN_TOKEN=' .env | cut -d'=' -f2- | tr -d '\\r\\n' | (pbcopy 2>/dev/null || xclip -selection clipboard 2>/dev/null || wl-copy 2>/dev/null || echo \"[Copie la línea ADMIN_TOKEN de .env]\")"
echo "================================================================="
