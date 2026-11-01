$ErrorActionPreference = 'Stop'
docker compose up --build -d
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host 'CIVIA scaffold: http://localhost:8000/health (aun no es la aplicacion completa)'
