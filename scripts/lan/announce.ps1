param(
    [Parameter(Mandatory)][string]$Address,
    [Parameter(Mandatory)][int]$InterfaceIndex,
    [Parameter(Mandatory)][int]$Port,
    [Parameter(Mandatory)][string]$TlsName,
    [Parameter(Mandatory)][Guid]$Installation,
    [Parameter(Mandatory)][string]$Token
)
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '../..')
$state = Join-Path (Get-Location).Path '.civia/lan'
$tokenFile = Join-Path $state 'mdns.token'
$statusFile = Join-Path $state 'mdns.status'
$ca = Join-Path $state 'ca.crt'

function Test-CiviaAnnouncement {
    return (Test-Path -LiteralPath $tokenFile) -and (Get-Content -Raw -LiteralPath $tokenFile).Trim() -eq $Token
}

function Get-CiviaGateway([string]$Route) {
    $body = curl.exe -q --ssl-revoke-best-effort --noproxy '*' --silent --fail --max-time 3 --cacert $ca --resolve "${TlsName}:${Port}:${Address}" "https://${TlsName}:${Port}$Route"
    if ($LASTEXITCODE -eq 0) { return ($body | ConvertFrom-Json) }
}

$mutex = [Threading.Mutex]::new($false, "Local\CIVIA-mDNS-$Installation")
$locked = $false
$service = $null
try {
    try { $locked = $mutex.WaitOne(10000) } catch [Threading.AbandonedMutexException] { $locked = $true }
    if (-not $locked -or -not (Test-CiviaAnnouncement)) { return }
    Add-Type -Path (Join-Path $PSScriptRoot 'WindowsDiscovery.cs')
    while (Test-CiviaAnnouncement) {
        $adapter = Get-NetIPAddress -InterfaceIndex $InterfaceIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue |
            Where-Object { $_.IPAddress -eq $Address -and $_.AddressState -eq 'Preferred' }
        $health = if ($adapter) { Get-CiviaGateway '/health' }
        $meta = if ($health.status -eq 'ok') { Get-CiviaGateway '/api/meta' }
        if ($meta.protocol -eq 1 -and $meta.installation_id -eq $Installation.ToString()) {
            if (-not $service) {
                $service = [CiviaDiscovery]::new($InterfaceIndex, $Address, $TlsName, $Port, $Installation)
                Set-Content -LiteralPath $statusFile -Value 'published' -Encoding Ascii
            }
        } elseif ($service) {
            $service.Dispose()
            $service = $null
            Set-Content -LiteralPath $statusFile -Value 'unavailable' -Encoding Ascii
        }
        Start-Sleep -Seconds 3
    }
} catch {
    if (Test-CiviaAnnouncement) { Set-Content -LiteralPath $statusFile -Value 'unavailable' -Encoding Ascii }
} finally {
    try { if ($service) { $service.Dispose() } } catch { }
    if ($locked) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
