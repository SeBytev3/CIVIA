# CIVIA - Script de Arranque y Despliegue Autonomo (Windows 11)
$ErrorActionPreference = 'Stop'

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host " CIVIA - Despliegue Autonomo Local (Santiago de Cali / UCC)" -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan

# 1. Comprobacion de Docker CLI disponible
$dockerCmd = Get-Command 'docker' -ErrorAction SilentlyContinue
if (-not $dockerCmd) {
    Write-Error "ERROR: Docker no se encuentra instalado o no esta en el PATH del sistema. Por favor instale Docker Desktop."
    exit 1
}

# 2. Comprobacion de Docker Engine activo
$dockerInfo = & docker info 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Error "ERROR: El demonio de Docker (Docker Desktop Engine) no esta respondiendo. Por favor inicie Docker Desktop y espere a que este en ejecucion."
    exit 1
}

# 3. Comprobacion de Docker Compose
$composeVersion = & docker compose version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Error "ERROR: 'docker compose' no esta disponible. Verifique que Docker Compose v2 este habilitado."
    exit 1
}

# 4. Generacion y proteccion de .env
$isFreshEnv = -not (Test-Path '.env')
if ($isFreshEnv) {
    if (-not (Test-Path '.env.example')) {
        Write-Error "ERROR: No se encontro el archivo '.env.example' como plantilla."
        exit 1
    }
    Copy-Item '.env.example' '.env'
    Write-Host "[OK] Archivo de configuracion local .env inicializado desde .env.example." -ForegroundColor Green
}

$envContent = Get-Content '.env' -Raw

# 5. Generacion CSPRNG de ADMIN_TOKEN si esta ausente o no cumple politica
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
    Write-Host "[OK] ADMIN_TOKEN robusto y unico generado con CSPRNG en .env (protegido)." -ForegroundColor Green
}

# 6 & 7. Generacion de POSTGRES_PASSWORD para instalaciones nuevas (sin rotar si ya existe BD previa)
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

# 7b. Deteccion y solicitud opcional de credenciales de IA
$envLines = Get-Content '.env'
$keyPrimary = ""
$keySecondary = ""
$keyGroq = ""
foreach ($l in $envLines) {
    if ($l -match '^GOOGLE_API_KEY_PRIMARY=(.*)$') { $keyPrimary = $matches[1].Trim() }
    elseif ($l -match '^GOOGLE_API_KEY_SECONDARY=(.*)$') { $keySecondary = $matches[1].Trim() }
    elseif ($l -match '^GROQ_API_KEY=(.*)$') { $keyGroq = $matches[1].Trim() }
}

$hasMissingKeys = [string]::IsNullOrWhiteSpace($keyPrimary) -or [string]::IsNullOrWhiteSpace($keySecondary) -or [string]::IsNullOrWhiteSpace($keyGroq)

if ($hasMissingKeys -and [Environment]::UserInteractive -and (-not $env:CI) -and (-not $env:NON_INTERACTIVE)) {
    Write-Host "`n[AVISO] Credenciales de IA externas pendientes en .env." -ForegroundColor Yellow
    Write-Host "CIVIA opera plenamente en Modo MVP Local sin claves externas (alta, foto, GPS, mapa, catalogo sintetico)." -ForegroundColor White
    $askKeys = Read-Host "Desea configurar ahora las claves de Google AI Studio / Groq? (s/N)"
    if ($askKeys.Trim().ToLower() -eq 's') {
        if ([string]::IsNullOrWhiteSpace($keyPrimary)) {
            Write-Host "Google AI Studio Primaria (gemini-3.8-flash) [entrada oculta, Enter para omitir]:" -ForegroundColor Yellow
            $sec = Read-Host -AsSecureString
            $b = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
            $p = [System.Runtime.InteropServices.Marshal]::PtrToStringBSTR($b)
            [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($b)
            if (-not [string]::IsNullOrWhiteSpace($p)) {
                $envRaw = Get-Content '.env' -Raw
                $envRaw = [regex]::Replace($envRaw, '(?m)^GOOGLE_API_KEY_PRIMARY=.*$', "GOOGLE_API_KEY_PRIMARY=$($p.Trim())")
                Set-Content -Path '.env' -Value $envRaw -NoNewline
                $keyPrimary = $p.Trim()
            }
        }
        if ([string]::IsNullOrWhiteSpace($keySecondary)) {
            Write-Host "Google AI Studio Secundaria (gemini-3.5-flash-lite) [entrada oculta, Enter para omitir]:" -ForegroundColor Yellow
            $sec = Read-Host -AsSecureString
            $b = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
            $p = [System.Runtime.InteropServices.Marshal]::PtrToStringBSTR($b)
            [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($b)
            if (-not [string]::IsNullOrWhiteSpace($p)) {
                $envRaw = Get-Content '.env' -Raw
                $envRaw = [regex]::Replace($envRaw, '(?m)^GOOGLE_API_KEY_SECONDARY=.*$', "GOOGLE_API_KEY_SECONDARY=$($p.Trim())")
                Set-Content -Path '.env' -Value $envRaw -NoNewline
                $keySecondary = $p.Trim()
            }
        }
        if ([string]::IsNullOrWhiteSpace($keyGroq)) {
            Write-Host "Groq Cloud Fallback (qwen/qwen3.8-27b) [entrada oculta, Enter para omitir]:" -ForegroundColor Yellow
            $sec = Read-Host -AsSecureString
            $b = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
            $p = [System.Runtime.InteropServices.Marshal]::PtrToStringBSTR($b)
            [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($b)
            if (-not [string]::IsNullOrWhiteSpace($p)) {
                $envRaw = Get-Content '.env' -Raw
                $envRaw = [regex]::Replace($envRaw, '(?m)^GROQ_API_KEY=.*$', "GROQ_API_KEY=$($p.Trim())")
                Set-Content -Path '.env' -Value $envRaw -NoNewline
                $keyGroq = $p.Trim()
            }
        }
    }
} elseif ($hasMissingKeys) {
    Write-Host "[INFO] Claves de IA pendientes. CIVIA iniciara en Modo MVP Local (sin inferencia remota)." -ForegroundColor Yellow
    Write-Host "       Para configurarlas despues sin reinstalar la BD: .\scripts\setup_ai_keys.ps1" -ForegroundColor Gray
}

# 8. Comprobacion de colision de red Docker (172.28.0.0/16)
$existingNetworks = & docker network ls --format "{{.Name}}" 2>&1
$civiaNetExists = $existingNetworks -match '^(civia_net|civia_civia_net)$'
if (-not $civiaNetExists) {
    $inspectAll = & docker network inspect (& docker network ls -q) 2>&1
    if ($inspectAll -match '172\.28\.0\.') {
        Write-Warning "AVISO: Se detecto otra red Docker utilizando la subred 172.28.0.0/16."
        Write-Warning "Si docker compose up falla por conflicto de red, revise las redes activas con 'docker network ls'."
    }
}

# 9. Despliegue con Docker Compose
Write-Host "Construyendo y levantando contenedores (PostgreSQL 17, FastAPI, Nginx PWA)..." -ForegroundColor Yellow
& docker compose up --build -d
if ($LASTEXITCODE -ne 0) {
    Write-Error "ERROR: Fallo el comando 'docker compose up --build -d'. Revise los logs con 'docker compose logs'."
    exit $LASTEXITCODE
}

# 10. Espera activa de verificacion de salud
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
    Write-Warning "Los servicios tardaron mas de lo esperado en responder. Compruebe los logs con: docker compose logs"
} else {
    Write-Host "[OK] Servicios base activos y saludables." -ForegroundColor Green
}

# 11. Comprobacion de estado de proveedores de IA en el contenedor
$aiProvidersStatus = $null
try {
    $aiJson = & docker compose exec -T api python -m app.validate_providers --json 2>$null
    if ($LASTEXITCODE -eq 0 -and $aiJson -match '\{') {
        $aiProvidersStatus = $aiJson | ConvertFrom-Json
    }
} catch {}

$primaryStatus = if ($aiProvidersStatus) { $aiProvidersStatus.google_primary.status } elseif (-not [string]::IsNullOrWhiteSpace($keyPrimary)) { "CONFIGURADA" } else { "PENDIENTE" }
$secondaryStatus = if ($aiProvidersStatus) { $aiProvidersStatus.google_secondary.status } elseif (-not [string]::IsNullOrWhiteSpace($keySecondary)) { "CONFIGURADA" } else { "PENDIENTE" }
$groqStatus = if ($aiProvidersStatus) { $aiProvidersStatus.groq.status } elseif (-not [string]::IsNullOrWhiteSpace($keyGroq)) { "CONFIGURADA" } else { "PENDIENTE" }

$frontendMsg = if ($healthy) { "DISPONIBLE (http://localhost:5173)" } else { "FALLIDO" }
$postgresMsg = if ($healthy) { "CONECTADO (Esquema listo)" } else { "FALLIDO" }
$apiMsg = if ($healthy) { "SALUDABLE (http://localhost:8000/docs)" } else { "FALLIDA" }

Write-Host "`n=================================================================" -ForegroundColor Cyan
Write-Host " RESULTADO OBLIGATORIO DEL ARRANQUE - CIVIA" -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host " - Frontend PWA:             $frontendMsg" -ForegroundColor White
Write-Host " - PostgreSQL 17:            $postgresMsg" -ForegroundColor White
Write-Host " - API REST & Swagger:       $apiMsg" -ForegroundColor White
Write-Host " - Google IA primaria:       $primaryStatus" -ForegroundColor $(if ($primaryStatus -eq 'VALIDADA') { 'Green' } elseif ($primaryStatus -eq 'CONFIGURADA') { 'Cyan' } else { 'Yellow' })
Write-Host " - Google IA secundaria:     $secondaryStatus" -ForegroundColor $(if ($secondaryStatus -eq 'VALIDADA') { 'Green' } elseif ($secondaryStatus -eq 'CONFIGURADA') { 'Cyan' } else { 'Yellow' })
Write-Host " - Groq Cloud:               $groqStatus" -ForegroundColor $(if ($groqStatus -eq 'VALIDADA') { 'Green' } elseif ($groqStatus -eq 'CONFIGURADA') { 'Cyan' } else { 'Yellow' })

if ($primaryStatus -eq "PENDIENTE" -and $groqStatus -eq "PENDIENTE") {
    Write-Host "`n [MODO MVP LOCAL ACTIVO]: Inferencia remota en vivo pendiente de claves." -ForegroundColor Yellow
    Write-Host " El sistema opera 100% en modo local (alta de reportes, foto, mapa, GPS y catalogo sintetico)." -ForegroundColor Gray
    Write-Host " Para configurar credenciales en cualquier momento sin tocar la base de datos:" -ForegroundColor Gray
    Write-Host "   .\scripts\setup_ai_keys.ps1" -ForegroundColor White
}

Write-Host "`n=================================================================" -ForegroundColor Cyan
Write-Host " INSTRUCCIONES DE ACCESO ADMINISTRATIVO" -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host " 1. Abra CIVIA en su navegador: http://localhost:5173" -ForegroundColor White
Write-Host " 2. Ingrese a la pestana 'Administracion'." -ForegroundColor White
Write-Host " 3. La clave administrativa fue generada y guardada de forma segura en .env." -ForegroundColor White
Write-Host " 4. Para copiarla al portapapeles sin mostrarla en pantalla ni logs, ejecute:" -ForegroundColor White
Write-Host '    powershell -Command "Get-Content .env | Select-String ''^ADMIN_TOKEN='' | ForEach-Object { $_.Line.Split(''='',2)[1].Trim() } | Set-Clipboard; Write-Host ''ADMIN_TOKEN copiado al portapapeles.''"' -ForegroundColor Gray
Write-Host "=================================================================" -ForegroundColor Cyan
