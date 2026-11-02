#!/usr/bin/env sh
set -eu
if [ ! -f .env ]; then
  cp .env.example .env
fi
if ! grep -Eq '^ADMIN_TOKEN=[A-Za-z0-9_-]{32,256}$' .env; then
  GEN_TOKEN="$(head -c 32 /dev/urandom | base64 | tr '+/' '-_' | tr -d '=\n\r')"
  if grep -q '^ADMIN_TOKEN=' .env; then
    sed -i "s/^ADMIN_TOKEN=.*/ADMIN_TOKEN=${GEN_TOKEN}/" .env
  else
    printf "\nADMIN_TOKEN=%s\n" "${GEN_TOKEN}" >> .env
  fi
  printf 'Se genero un ADMIN_TOKEN unico y robusto en .env para esta instalacion.\n'
fi
docker compose up --build -d
printf 'CIVIA en ejecucion -> PWA Ciudadana: http://localhost:5173 | API Backend: http://localhost:8000/health\n'
