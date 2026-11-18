param([switch]$InitializeOnly)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)

function New-CiviaSecret {
    $bytes = New-Object byte[] 32
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    return ([Convert]::ToBase64String($bytes)).TrimEnd('=').Replace('+','-').Replace('/','_')
}

function Read-CiviaSetting([string]$Name) {
    $match = [regex]::Match($script:EnvText, "(?m)^$Name=([^\r\n]*)")
    return $match.Groups[1].Value.Trim().Trim('"').Trim("'")
}

function Add-CiviaSetting([string]$Name, [string]$Value) {
    if (Read-CiviaSetting $Name) { return }
    if ($script:EnvText -match "(?m)^$Name=[^\r\n]*") {
        $script:EnvText = [regex]::Replace($script:EnvText, "(?m)^$Name=[^\r\n]*", { param($m) "$Name=$Value" })
    } else {
        $script:EnvText = $script:EnvText.TrimEnd() + "`r`n$Name=$Value`r`n"
    }
}

$EnvText = if (Test-Path -LiteralPath '.env') {
    Get-Content -Raw -LiteralPath '.env'
} else { Get-Content -Raw -LiteralPath '.env.example' }
Add-CiviaSetting POSTGRES_DB 'civia'
Add-CiviaSetting POSTGRES_USER 'civia'
Add-CiviaSetting POSTGRES_PASSWORD (New-CiviaSecret)
Add-CiviaSetting ADMIN_TOKEN (New-CiviaSecret)
$dbName = [Uri]::EscapeDataString((Read-CiviaSetting POSTGRES_DB))
$dbUser = [Uri]::EscapeDataString((Read-CiviaSetting POSTGRES_USER))
$dbPassword = [Uri]::EscapeDataString((Read-CiviaSetting POSTGRES_PASSWORD))
Add-CiviaSetting DATABASE_URL "postgresql://${dbUser}:${dbPassword}@db:5432/$dbName"
foreach ($role in @{ APP = 'civia_app'; AGENT = 'civia_agent'; WORKER = 'civia_worker' }.GetEnumerator()) {
    Add-CiviaSetting "$($role.Key)_DATABASE_URL" "postgresql://$($role.Value):$(New-CiviaSecret)@db:5432/$dbName"
}
$envPath = Join-Path (Get-Location).Path '.env'
[IO.File]::WriteAllText($envPath, $EnvText, [Text.UTF8Encoding]::new($false))
if ($InitializeOnly) { return }

docker compose up --build -d --wait --wait-timeout 120
if ($LASTEXITCODE -ne 0) { throw 'El arranque falló. Consulte docker compose ps -a y los logs locales.' }
$health = Invoke-RestMethod -Uri 'http://localhost:8000/health' -TimeoutSec 8
if ($health.status -ne 'ok') { throw 'La API no confirmó el arranque.' }
Write-Host 'Portal administrativo PWA  http://localhost:5173/admin/'
Write-Host 'Contingencia web móvil      http://localhost:5173/'
Write-Host 'API y PostgreSQL saludables  http://localhost:8000/docs'
docker compose ps worker
docker compose exec -T api python -m app.validate_providers
docker compose exec -T api python -m app.bootstrap_admins --status
Write-Host 'Administradores iniciales   docker compose exec api python -m app.bootstrap_admins'
Write-Host 'Claves de IA                .\scripts\setup_ai_keys.ps1'
Write-Host 'Android y conectividad      docs/ANDROID_BUILD.md'
