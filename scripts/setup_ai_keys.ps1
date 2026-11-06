# CIVIA - Script de Configuracion Segura de Claves de IA (Windows 11)
param(
    [string]$GoogleKeyPrimary = "",
    [string]$GoogleKeySecondary = "",
    [string]$GroqKey = "",
    [switch]$ValidateLive,
    [switch]$NonInteractive
)

$ErrorActionPreference = 'Stop'

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host " CIVIA - Configuracion Segura de Credenciales de IA" -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan

if (-not (Test-Path '.env')) {
    if (Test-Path '.env.example') {
        Copy-Item '.env.example' '.env'
        Write-Host "[OK] .env inicializado desde .env.example." -ForegroundColor Green
    } else {
        Write-Error "ERROR: No se encontro .env ni .env.example en la raiz del repositorio."
        exit 1
    }
}

$envLines = Get-Content '.env'
$currentPrimary = ""
$currentSecondary = ""
$currentGroq = ""

foreach ($line in $envLines) {
    if ($line -match '^GOOGLE_API_KEY_PRIMARY=(.*)$') {
        $currentPrimary = $matches[1].Trim()
    } elseif ($line -match '^GOOGLE_API_KEY_SECONDARY=(.*)$') {
        $currentSecondary = $matches[1].Trim()
    } elseif ($line -match '^GROQ_API_KEY=(.*)$') {
        $currentGroq = $matches[1].Trim()
    }
}

$isInteractive = (-not $NonInteractive) -and [Environment]::UserInteractive

function SecurePromptKey([string]$providerName, [string]$currentVal, [string]$cliVal) {
    if ($cliVal -ne "") {
        return $cliVal
    }
    if (-not $isInteractive) {
        return $currentVal
    }
    
    if ($currentVal -ne "") {
        Write-Host "[$providerName] Ya se encuentra configurada en .env." -ForegroundColor Cyan
        $choice = Read-Host "Desea reemplazarla? (s/N)"
        if ($choice.Trim().ToLower() -ne "s") {
            return $currentVal
        }
    }
    
    Write-Host "Ingrese la clave para $providerName (entrada oculta, Enter para omitir):" -ForegroundColor Yellow
    $secureInput = Read-Host -AsSecureString
    $bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureInput)
    $plain = [System.Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    
    if ([string]::IsNullOrWhiteSpace($plain)) {
        return $currentVal
    }
    return $plain.Trim()
}

$newPrimary = SecurePromptKey "Google AI Studio (Primaria - gemini-3.8-flash)" $currentPrimary $GoogleKeyPrimary
$newSecondary = SecurePromptKey "Google AI Studio (Secundaria - gemini-3.5-flash-lite)" $currentSecondary $GoogleKeySecondary
$newGroq = SecurePromptKey "Groq Cloud (Fallback - qwen/qwen3.8-27b)" $currentGroq $GroqKey

# Actualizar .env sin exponer secretos ni alterar PostgreSQL ni tokens existentes
$envRaw = Get-Content '.env' -Raw

function UpdateEnvVar([string]$content, [string]$varName, [string]$val) {
    if ($content -match "(?m)^$varName=.*$") {
        return [regex]::Replace($content, "(?m)^$varName=.*$", "$varName=$val")
    } else {
        return $content.TrimEnd() + "`r`n$varName=$val`r`n"
    }
}

$envRaw = UpdateEnvVar $envRaw "GOOGLE_API_KEY_PRIMARY" $newPrimary
$envRaw = UpdateEnvVar $envRaw "GOOGLE_API_KEY_SECONDARY" $newSecondary
$envRaw = UpdateEnvVar $envRaw "GROQ_API_KEY" $newGroq

Set-Content -Path '.env' -Value $envRaw -NoNewline
Write-Host "[OK] Archivo .env local actualizado de forma protegida (excluido de Git)." -ForegroundColor Green

# Recrear exclusivamente el contenedor de la API para propagar las variables sin afectar PostgreSQL
Write-Host "Recargando variables en el contenedor de API (sin tocar base de datos)..." -ForegroundColor Yellow
& docker compose up -d --no-deps api
if ($LASTEXITCODE -ne 0) {
    Write-Error "ERROR al recargar el servicio api."
    exit $LASTEXITCODE
}

# Esperar a que la API responda salud
Start-Sleep -Seconds 2
$apiReady = $false
for ($i = 1; $i -le 10; $i++) {
    try {
        $h = & curl.exe -s --max-time 3 http://127.0.0.1:8000/health 2>&1
        if ($h -match '"status":\s*"ok"') {
            $apiReady = $true
            break
        }
    } catch {}
    Start-Sleep -Seconds 1
}

if (-not $apiReady) {
    Write-Warning "AVISO: La API tardo en reiniciar. Verifique con: docker compose logs api"
}

# Ejecutar comprobacion en el contenedor
Write-Host "`nVerificando variables dentro del contenedor api:" -ForegroundColor Cyan
if ($ValidateLive) {
    & docker compose exec -T api python -m app.validate_providers --live
} else {
    & docker compose exec -T api python -m app.validate_providers
}

Write-Host "`n=================================================================" -ForegroundColor Cyan
Write-Host " INSTRUCCIONES DE ACCESO ADMINISTRATIVO" -ForegroundColor Yellow
Write-Host " 1. Abra CIVIA en su navegador: http://localhost:5173" -ForegroundColor White
Write-Host " 2. Ingrese a la pestana 'Administracion'." -ForegroundColor White
Write-Host " 3. El ADMIN_TOKEN generado reside en su archivo .env local." -ForegroundColor White
Write-Host " 4. Para copiarlo al portapapeles sin mostrarlo en pantalla ni logs, ejecute:" -ForegroundColor White
Write-Host '    powershell -Command "Get-Content .env | Select-String ''^ADMIN_TOKEN='' | ForEach-Object { $_.Line.Split(''='',2)[1].Trim() } | Set-Clipboard; Write-Host ''ADMIN_TOKEN copiado al portapapeles.''"' -ForegroundColor Gray
Write-Host "=================================================================" -ForegroundColor Cyan
