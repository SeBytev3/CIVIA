function Protect-CiviaPath([string]$Path) {
    $owner = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $system = 'S-1-5-18'
    $permissions = if (Test-Path -LiteralPath $Path -PathType Container) { '(OI)(CI)F' } else { 'F' }
    & icacls.exe $Path /inheritance:r /grant:r "*${owner}:$permissions" "*${system}:$permissions" /Q | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "No se pudo proteger $Path." }
    $access = (Get-Acl -LiteralPath $Path).GetAccessRules($true, $false, [Security.Principal.SecurityIdentifier])
    foreach ($identity in @($access | ForEach-Object { $_.IdentityReference.Value } | Sort-Object -Unique)) {
        if ($identity -ne $owner -and $identity -ne $system) {
            & icacls.exe $Path /remove "*$identity" /Q | Out-Null
            if ($LASTEXITCODE -ne 0) { throw "No se pudo restringir el acceso a $Path." }
        }
    }
}

function Get-CiviaPort([string]$Setting, [int]$Default) {
    $value = [Environment]::GetEnvironmentVariable($Setting)
    if (-not $value) { $value = Read-CiviaSetting $Setting }
    if (-not $value) { return $Default }
    if ($value -notmatch '^\d{1,5}$' -or [int]$value -lt 1 -or [int]$value -gt 65535) {
        throw "Configura $Setting con un puerto entre 1 y 65535."
    }
    return [int]$value
}

function Get-CiviaLanInterface([string]$Address) {
    $adapters = Get-NetAdapter -Physical | Where-Object Status -eq 'Up'
    $candidates = @(foreach ($adapter in $adapters) {
        Get-NetIPAddress -InterfaceIndex $adapter.ifIndex -AddressFamily IPv4 |
            Where-Object { $_.AddressState -eq 'Preferred' -and $_.IPAddress -match '^(10\.|172\.(1[6-9]|2[0-9]|3[01])\.|192\.168\.)' }
    })
    if ($Address) { $candidates = @($candidates | Where-Object IPAddress -eq $Address) }
    if ($candidates.Count -ne 1) {
        throw 'Selecciona una IPv4 privada de un adaptador físico activo con -LanAddress.'
    }
    return $candidates[0]
}

function Assert-CiviaPort([string]$Service, [string]$Address, [int]$Port, [int]$Target) {
    $container = docker compose -f docker-compose.yml ps -q $Service
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo comprobar el puerto del despliegue.' }
    if ($container) {
        $ports = docker inspect --format '{{json .NetworkSettings.Ports}}' $container | ConvertFrom-Json
        $existing = $ports.PSObject.Properties["$Target/tcp"]
        if ($existing -and @($existing.Value | Where-Object { $_.HostIp -in @($Address, '0.0.0.0', '::') -and $_.HostPort -eq "$Port" }).Count) { return }
    }
    $socket = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Parse($Address), $Port)
    $socket.ExclusiveAddressUse = $true
    try { $socket.Start() }
    catch { throw "El puerto $Port no está disponible en $Address. Libéralo o configura otro puerto de CIVIA." }
    finally { $socket.Stop() }
}

function Get-CiviaIPv4Range([string]$Subnet) {
    $address, $length = $Subnet.Split('/')
    if ($length -notmatch '^\d{1,2}$' -or [int]$length -gt 32) { throw 'Configura CIVIA_SUBNET con un CIDR IPv4 válido.' }
    $bytes = [Net.IPAddress]::Parse($address).GetAddressBytes()
    if ($bytes.Length -ne 4) { throw 'Configura CIVIA_SUBNET con un CIDR IPv4 válido.' }
    [Array]::Reverse($bytes)
    $span = [long][Math]::Pow(2, 32 - [int]$length)
    $start = [long][BitConverter]::ToUInt32($bytes, 0)
    $start -= $start % $span
    return @($start, ($start + $span - 1))
}

function New-CiviaIsolatedSettings {
    $keys = 'COMPOSE_PROJECT_NAME', 'CIVIA_SUBNET', 'CIVIA_GATEWAY', 'CIVIA_DYNAMIC_RANGE', 'CIVIA_FRONTEND_IP', 'CIVIA_API_PORT', 'CIVIA_HTTP_PORT'
    foreach ($key in $keys) {
        if ([Environment]::GetEnvironmentVariable($key)) { throw "Quita $key del entorno antes de usar -Isolated." }
    }
    $networks = @(docker network ls -q)
    if ($LASTEXITCODE -ne 0) { throw 'Abre Docker antes de preparar el clon aislado.' }
    $occupied = @(foreach ($network in $networks) {
        $ranges = @(docker network inspect --format '{{range .IPAM.Config}}{{println .Subnet}}{{end}}' $network)
        if ($LASTEXITCODE -ne 0) { throw 'Docker no confirmó las subredes existentes.' }
        foreach ($range in $ranges) {
            if ($range -match '^\d+(\.\d+){3}/\d+$') { ,@(Get-CiviaIPv4Range $range) }
        }
    })
    $prefix = $null
    foreach ($index in 240..254) {
        $candidate = "172.29.$index"
        $first, $last = Get-CiviaIPv4Range "$candidate.0/24"
        if (-not @($occupied | Where-Object { $first -le $_[1] -and $_[0] -le $last }).Count) {
            $prefix = $candidate
            break
        }
    }
    if (-not $prefix) { throw 'No se encontró una subred Docker para el clon aislado.' }
    $listeners = @([Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0), [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0))
    try {
        foreach ($listener in $listeners) { $listener.Start() }
        return [ordered]@{
            COMPOSE_PROJECT_NAME = 'civia_' + [Guid]::NewGuid().ToString('N').Substring(0, 12)
            CIVIA_SUBNET = "$prefix.0/24"
            CIVIA_GATEWAY = "$prefix.1"
            CIVIA_DYNAMIC_RANGE = "$prefix.128/25"
            CIVIA_FRONTEND_IP = "$prefix.2"
            CIVIA_API_PORT = $listeners[0].LocalEndpoint.Port
            CIVIA_HTTP_PORT = $listeners[1].LocalEndpoint.Port
        }
    } finally { foreach ($listener in $listeners) { $listener.Stop() } }
}

function Assert-CiviaNetwork {
    $project = if ($env:COMPOSE_PROJECT_NAME) { $env:COMPOSE_PROJECT_NAME } else { Read-CiviaSetting COMPOSE_PROJECT_NAME }
    if (-not $project) { $project = (Split-Path (Get-Location).Path -Leaf).ToLowerInvariant() -replace '[^a-z0-9_-]','' }
    $subnet = if ($env:CIVIA_SUBNET) { $env:CIVIA_SUBNET } else { Read-CiviaSetting CIVIA_SUBNET }
    if (-not $subnet) { $subnet = '172.28.0.0/16' }
    $gateway = if ($env:CIVIA_GATEWAY) { $env:CIVIA_GATEWAY } else { Read-CiviaSetting CIVIA_GATEWAY }
    if (-not $gateway) { $gateway = '172.28.0.1' }
    $pool = if ($env:CIVIA_DYNAMIC_RANGE) { $env:CIVIA_DYNAMIC_RANGE } else { Read-CiviaSetting CIVIA_DYNAMIC_RANGE }
    if (-not $pool) { $pool = '172.28.1.0/24' }
    $reconcile = $false
    $start, $end = Get-CiviaIPv4Range $subnet
    $networks = @(docker network ls --format '{{.Name}}')
    if ($LASTEXITCODE -ne 0) { throw 'No se pudieron revisar las redes de Docker.' }
    foreach ($network in $networks) {
        if ($network -eq "${project}_civia_net") {
            $configuration = docker network inspect --format '{{index .Labels "com.docker.compose.project"}}|{{index .Labels "com.docker.compose.network"}}|{{.Driver}}|{{range .IPAM.Config}}{{.Subnet}}~{{.Gateway}}~{{.IPRange}};{{end}}' $network
            if ($LASTEXITCODE -ne 0) { throw "No se pudo revisar la red $network." }
            $networkProject, $label, $driver, $ipam = $configuration.Split('|')
            if ($networkProject -ne $project -or $label -ne 'civia_net' -or $driver -ne 'bridge') {
                throw "La red $network existe y no pertenece al proyecto Compose de CIVIA. Usa un nombre de proyecto distinto."
            }
            $reconcile = $ipam -cne "$subnet~$gateway~$pool;"
            continue
        }
        $ranges = @(docker network inspect --format '{{range .IPAM.Config}}{{println .Subnet}}{{end}}' $network)
        foreach ($range in $ranges) {
            if ($range -notmatch '^\d+\.\d+\.\d+\.\d+/\d+$') { continue }
            $otherStart, $otherEnd = Get-CiviaIPv4Range $range
            if ($start -le $otherEnd -and $otherStart -le $end) {
                throw "La red $subnet se superpone con la red Docker $network ($range). Configura un bloque CIVIA libre en .env."
            }
        }
    }
    return $reconcile
}
