# CIVIA — Script de Arranque y Despliegue Autónomo (Windows 11)
$ErrorActionPreference = 'Stop'

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host " CIVIA — Despliegue Autónomo Local (Santiago de Cali / UCC)" -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan

# 1. Comprobación de Docker CLI disponible
$dockerCmd = Get-Command 'docker' -ErrorAction SilentlyContinue
if (-not $dockerCmd) {
    Write-Error "ERROR: Docker no se encuentra instalado o no está en el PATH del sistema. Por favor instale Docker Desktop."
    exit 1
}

# 2. Comprobación de Docker Engine activo
$dockerInfo = & docker info 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Error "ERROR: El demonio de Docker (Docker Desktop Engine) no está respondiendo. Por favor inicie Docker Desktop y espere a que esté en ejecución."
    exit 1
}

# 3. Comprobación de Docker Compose
$composeVersion = & docker compose version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Error "ERROR: 'docker compose' no está disponible. Verifique que Docker Compose v2 esté habilitado."
    exit 1
}

# 4. Generación y protección de .env
$isFreshEnv = -not (Test-Path '.env')
if ($isFreshEnv) {
    if (-not (Test-Path '.env.example')) {
        Write-Error "ERROR: No se encontró el archivo '.env.example' como plantilla."
        exit 1
    }
    Copy-Item '.env.example' '.env'
    Write-Host "[OK] Archivo de configuración local .env inicializado desde .env.example." -ForegroundColor Green
}

$envContent = Get-Content '.env' -Raw

# 5. Generación CSPRNG de ADMIN_TOKEN si está ausente o no cumple política
if ($envContent -match '(?m)^ADMIN_TOKEN=\s*$' -or $envContent -notmatch '(?m)^ADMIN_TOKEN=[A-Za-z0-9_-]{32,256}\r?$') {
    $tokenBytes = New-Object byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($tokenBytes)
    $generatedToken = ([Convert]::ToBase64String($tokenBytes)).TrimEnd('=').Replace('+', '-').Replace('/', '_')
    if ($envContent -match '(?m)^ADMIN_TOKEN=.*$') {
        $envContent = [regex]::Replace($envContent, '(?m)^ADMIN_TOKEN=.*$', "ADMIN_TOKEN=$generatedToken")
    } else {
        $envContent = $envContent.TrimEnd() + "`r`nADMIN_TOKEN=$generatedToken`r`n"
    }
    Set-Content -Path '.env' -Value $envContent -NoNewline
    Write-Host "[OK] ADMIN_TOKEN robusto y único generado con CSPRNG en .env (protegido)." -ForegroundColor Green
}

# 6 & 7. Generación de POSTGRES_PASSWORD para instalaciones nuevas (sin rotar si ya existe BD previa)
if ($isFreshEnv) {
    $pwChars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $pwBytes = New-Object byte[] 24
    $rng.GetBytes($pwBytes)
    $genPassword = ""
    for ($i = 0; $i -lt 24; $i++) {
        $genPassword += $pwChars[$pwBytes[$i] % $pwChars.Length]
    }
    $envContent = Get-Content '.env' -Raw
    $envContent = [regex]::Replace($envContent, '(?m)^POSTGRES_PASSWORD=.*$', "POSTGRES_PASSWORD=$genPassword")
    $envContent = [regex]::Replace($envContent, '(?m)^DATABASE_URL=.*$', "DATABASE_URL=postgresql://civia:$genPassword@db:5432/civia")
    Set-Content -Path '.env' -Value $envContent -NoNewline
    Write-Host "[OK] Credenciales seguras para PostgreSQL configuradas en .env." -ForegroundColor Green
}

# 8. Comprobación de colisión de red Docker (172.28.0.0/16)
$existingNetworks = & docker network ls --format "{{.Name}}" 2>&1
$civiaNetExists = $existingNetworks -match '^(civia_net|civia_civia_net)$'
if (-not $civiaNetExists) {
    $inspectAll = & docker network inspect (& docker network ls -q) 2>&1
    if ($inspectAll -match '172\.28\.0\.') {
        Write-Warning "AVISO: Se detectó otra red Docker utilizando la subred 172.28.0.0/16."
        Write-Warning "Si docker compose up falla por conflicto de red, revise las redes activas con 'docker network ls'."
    }
}

# 9. Despliegue con Docker Compose
Write-Host "Construyendo y levantando contenedores (PostgreSQL 17, FastAPI, Nginx PWA)..." -ForegroundColor Yellow
& docker compose up --build -d
if ($LASTEXITCODE -ne 0) {
    Write-Error "ERROR: Falló el comando 'docker compose up --build -d'. Revise los logs con 'docker compose logs'."
    exit $LASTEXITCODE
}

# 10. Espera activa de verificación de salud
Write-Host "Verificando disponibilidad de servicios..." -ForegroundColor Yellow
$maxRetries = 20
$healthy = $false
for ($attempt = 1; $attempt -le $maxRetries; $attempt++) {
    Start-Sleep -Seconds 2
    try {
        $healthJson = & curl.exe -s --max-time 3 http://127.0.0.1:8000/health 2>&1
        if ($healthJson -match '"status":\s*"ok"' -and $healthJson -match '"connected":\s*true') {
            $frontendCheck = & curl.exe -s -I --max-time 3 http://127.0.0.1:5173 2>&1
            if ($frontendCheck -match 'HTTP/1\.[01]\s+200') {
                $healthy = $true
                break
            }
        }
    } catch {
        # Reintentar en siguiente ciclo
    }
}

if (-not $healthy) {
    Write-Warning "Los servicios tardaron más de lo esperado en responder. Compruebe los logs con: docker compose logs"
} else {
    Write-Host "[OK] Todos los servicios se encuentran activos y saludables." -ForegroundColor Green
}

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host " CIVIA DESPLEGADO CON ÉXITO" -ForegroundColor Green
Write-Host " - Aplicación Web PWA:   http://localhost:5173" -ForegroundColor White
Write-Host " - API Backend & Docs:   http://localhost:8000/docs" -ForegroundColor White
Write-Host " - Health Check:         http://localhost:8000/health" -ForegroundColor White
Write-Host "=================================================================" -ForegroundColor Cyan
