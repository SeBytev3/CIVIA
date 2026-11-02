$ErrorActionPreference = 'Stop'
if (-not (Test-Path '.env')) {
    Copy-Item '.env.example' '.env'
}
$envContent = Get-Content '.env' -Raw
if ($envContent -match '(?m)^ADMIN_TOKEN=\s*$' -or $envContent -notmatch '(?m)^ADMIN_TOKEN=.{24,}') {
    $bytes = New-Object byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $generatedToken = 'civia_adm_' + ([Convert]::ToBase64String($bytes) -replace '[+/=]', '')
    if ($envContent -match '(?m)^ADMIN_TOKEN=.*$') {
        $envContent = [regex]::Replace($envContent, '(?m)^ADMIN_TOKEN=.*$', "ADMIN_TOKEN=$generatedToken")
    } else {
        $envContent = $envContent.TrimEnd() + "`r`nADMIN_TOKEN=$generatedToken`r`n"
    }
    Set-Content -Path '.env' -Value $envContent -NoNewline
    Write-Host 'Se genero un ADMIN_TOKEN unico y robusto en .env para esta instalacion.'
}
docker compose up --build -d
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host 'CIVIA en ejecucion -> PWA Ciudadana: http://localhost:5173 | API Backend: http://localhost:8000/health'
