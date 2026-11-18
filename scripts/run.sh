#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")/.."
source scripts/civia-env.sh
civia_initialize_env
if [[ "${1:-}" == --initialize-only ]]; then
    exit 0
fi

docker compose up --build -d --wait --wait-timeout 120
curl -fsS --max-time 8 http://localhost:8000/health >/dev/null
printf '%s\n' \
    'Portal administrativo PWA  http://localhost:5173/admin/' \
    'Contingencia web móvil      http://localhost:5173/' \
    'API y PostgreSQL saludables  http://localhost:8000/docs'
docker compose ps worker
docker compose exec -T api python -m app.validate_providers
if ! docker compose exec -T api python -m app.bootstrap_admins --status; then
    printf '%s\n' 'Inicializa las cuentas administrativas desde una terminal privada.'
fi
printf '%s\n' \
    'Administradores iniciales   docker compose exec api python -m app.bootstrap_admins' \
    'Claves de IA                ./scripts/setup_ai_keys.sh' \
    'Android y conectividad      docs/ANDROID_BUILD.md'
