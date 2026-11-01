$ErrorActionPreference = 'Stop'
docker compose up --build -d
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host 'CIVIA en ejecucion -> PWA Ciudadana: http://localhost:5173 | API Backend: http://localhost:8000/health'
