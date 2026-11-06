#!/usr/bin/env bash
set -euo pipefail

if [ ! -f .env ]; then
    cp .env.example .env
fi

if ! grep -qE '^ADMIN_TOKEN=[A-Za-z0-9_-]{32,256}$' .env 2>/dev/null; then
    GENERATED_TOKEN=$(openssl rand -base64 32 | tr -d '=' | tr '+/' '-_')
    if grep -q '^ADMIN_TOKEN=' .env; then
        sed -i.bak -E "s/^ADMIN_TOKEN=.*$/ADMIN_TOKEN=${GENERATED_TOKEN}/" .env && rm -f .env.bak
    else
        echo "ADMIN_TOKEN=${GENERATED_TOKEN}" >> .env
    fi
    echo "Se generó un ADMIN_TOKEN seguro en .env."
fi

docker compose up --build -d
echo "CIVIA en ejecución -> PWA Ciudadana: http://localhost:5173 | API Backend: http://localhost:8000/health"
