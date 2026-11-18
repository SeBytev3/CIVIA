param([switch]$InitializeOnly, [switch]$Stop, [switch]$Lan, [string]$LanAddress, [string]$LanName, [switch]$NoDiscovery, [switch]$Interactive, [switch]$Isolated)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
. (Join-Path $PSScriptRoot 'civia-host.ps1')
if (($LanAddress -or $LanName -or $NoDiscovery) -and -not $Lan) { throw 'Usa -Lan para estas opciones.' }
if ($Stop -and ($Lan -or $InitializeOnly -or $Interactive -or $Isolated)) { throw 'Usa -Stop independientemente.' }
if ($InitializeOnly -and ($Interactive -or $Isolated)) { throw 'Usa -InitializeOnly independientemente.' }
if ($Isolated -and (Test-Path -LiteralPath .env)) { throw '-Isolated corresponde al primer arranque de un clon sin .env.' }
if ($Interactive -and [Console]::IsInputRedirected) { throw '-Interactive requiere una terminal interactiva.' }

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

function Set-CiviaSetting([string]$Name, [string]$Value) {
    if ($script:EnvText -match "(?m)^$Name=[^\r\n]*") {
        $script:EnvText = [regex]::Replace($script:EnvText, "(?m)^$Name=[^\r\n]*", { param($m) "$Name=$Value" })
    } else {
        $script:EnvText = $script:EnvText.TrimEnd() + "`r`n$Name=$Value`r`n"
    }
}

function Add-CiviaSetting([string]$Name, [string]$Value) {
    if (-not (Read-CiviaSetting $Name)) { Set-CiviaSetting $Name $Value }
}

function Initialize-CiviaEnv {
    $envPath = Join-Path (Get-Location).Path '.env'
    $script:EnvText = if (Test-Path -LiteralPath $envPath) {
        [IO.File]::ReadAllText($envPath)
    } else { [IO.File]::ReadAllText((Join-Path (Get-Location).Path '.env.example')) }
    if ($Isolated) {
        $settings = New-CiviaIsolatedSettings
        foreach ($setting in $settings.GetEnumerator()) { Set-CiviaSetting $setting.Key $setting.Value }
    }
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
    if (-not (Test-Path -LiteralPath $envPath)) { [void](New-Item -ItemType File -Path $envPath) }
    Protect-CiviaPath $envPath
    if ([IO.File]::ReadAllText($envPath) -cne $script:EnvText) {
        [IO.File]::WriteAllText($envPath, $script:EnvText, [Text.UTF8Encoding]::new($false))
    }
}

if (-not $Stop) { Initialize-CiviaEnv }
if ($InitializeOnly) { return }
if ($Interactive -and ((-not (Read-CiviaSetting GOOGLE_API_KEY_PRIMARY)) -or (-not (Read-CiviaSetting GROQ_API_KEY)))) {
    if ((Read-Host '¿Quieres ingresar las claves de IA ahora? [s/N]') -match '^[sSyY]$') {
        & "$PSScriptRoot/setup_ai_keys.ps1" -ConfigureOnly
        $script:EnvText = [IO.File]::ReadAllText((Join-Path (Get-Location).Path '.env'))
    }
}
. (Join-Path $PSScriptRoot 'civia-run-host.ps1')
