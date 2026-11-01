#!/usr/bin/env sh
set -eu
docker compose up --build -d
printf 'CIVIA scaffold: http://localhost:8000/health (no es el MVP final)
'
