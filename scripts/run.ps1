param([switch]$InitializeOnly, [switch]$Stop, [switch]$Lan, [string]$LanAddress, [string]$LanName, [switch]$NoDiscovery)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
. (Join-Path $PSScriptRoot 'civia-host.ps1')
if (($LanAddress -or $LanName -or $NoDiscovery) -and -not $Lan) { throw 'Usa -Lan para estas opciones.' }
if ($Stop -and ($Lan -or $InitializeOnly)) { throw 'Usa -Stop independientemente.' }

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

function Initialize-CiviaEnv {
    $envPath = Join-Path (Get-Location).Path '.env'
    $script:EnvText = if (Test-Path -LiteralPath $envPath) {
        [IO.File]::ReadAllText($envPath)
    } else { [IO.File]::ReadAllText((Join-Path (Get-Location).Path '.env.example')) }
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
. (Join-Path $PSScriptRoot 'civia-run-host.ps1')
