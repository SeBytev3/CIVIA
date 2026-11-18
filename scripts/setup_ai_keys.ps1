param([switch]$ValidateLive, [switch]$NonInteractive)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)

& "$PSScriptRoot/run.ps1" -InitializeOnly
$envPath = Join-Path (Get-Location).Path '.env'
$envText = Get-Content -Raw -LiteralPath $envPath
if (-not $NonInteractive) {
    foreach ($name in 'GOOGLE_API_KEY_PRIMARY', 'GROQ_API_KEY') {
        $masked = Read-Host "$name (Enter para conservar u omitir)" -AsSecureString
        $buffer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($masked)
        try {
            $key = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($buffer).Trim()
            if (-not $key) { continue }
            if ($key -notmatch '^[A-Za-z0-9_-]+$') { throw 'Formato de credencial no válido.' }
            if ($envText -match "(?m)^$name=[^\r\n]*") {
                $envText = [regex]::Replace($envText, "(?m)^$name=[^\r\n]*", { param($m) "$name=$key" })
            } else { $envText = $envText.TrimEnd() + "`r`n$name=$key`r`n" }
        } finally {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($buffer)
            $masked.Dispose()
            $key = $null
        }
    }
}
[IO.File]::WriteAllText($envPath, $envText, [Text.UTF8Encoding]::new($false))
$apiId = docker compose ps -q api
if ($LASTEXITCODE -ne 0) { throw 'Docker Compose no está disponible.' }
if (-not $apiId) {
    Write-Host 'Configuración guardada. Inicie con .\scripts\run.ps1.'
    return
}
docker compose up -d --no-deps --wait api worker
if ($LASTEXITCODE -ne 0) { throw 'No se pudieron recargar API y worker.' }
$providerFlags = @()
if ($ValidateLive) { $providerFlags += '--live' }
docker compose exec -T api python -m app.validate_providers @providerFlags
if ($LASTEXITCODE -ne 0) { throw 'La comprobación de proveedores falló.' }
