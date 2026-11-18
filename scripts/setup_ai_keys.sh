#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")/.."
source scripts/civia-env.sh
civia_initialize_env
validate_flag=
case "${1:-}" in
    '') ;;
    --configure-only) ;;
    --validate-live) validate_flag=--live ;;
    *) printf '%s\n' 'Uso: ./scripts/setup_ai_keys.sh [--configure-only | --validate-live]' >&2; exit 2 ;;
esac

if [[ -t 0 ]]; then
    for name in GOOGLE_API_KEY_PRIMARY GROQ_API_KEY; do
        IFS= read -r -s -p "$name (Enter para conservar u omitir): " key
        printf '\n'
        if [[ -n "$key" ]]; then
            if [[ ! "$key" =~ ^[a-zA-Z0-9_-]+$ ]]; then
                printf '%s\n' 'Formato de credencial no válido.' >&2
                exit 2
            fi
            civia_write_setting "$name" "$key"
        fi
        unset key
    done
fi
if [[ "${1:-}" == --configure-only ]]; then exit 0; fi
if [[ -z "$(docker compose ps -q api)" ]]; then
    printf '%s\n' 'Configuración guardada. Inicie con ./scripts/run.sh.'
    exit 0
fi
docker compose up -d --no-deps --wait api worker
if [[ -n "$validate_flag" ]]; then
    docker compose exec -T api python -m app.validate_providers "$validate_flag"
else
    docker compose exec -T api python -m app.validate_providers
fi
