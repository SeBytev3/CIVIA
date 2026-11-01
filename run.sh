#!/usr/bin/env sh
set -eu
docker compose up --build -d
printf 'CIVIA en ejecucion -> PWA Ciudadana: http://localhost:5173 | API Backend: http://localhost:8000/health\n'
