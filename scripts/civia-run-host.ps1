$state = Join-Path (Get-Location).Path '.civia'
$accessState = Join-Path $state 'access'
$lanState = Join-Path $state 'lan'
$discoveryToken = Join-Path $lanState 'mdns.token'
$base = @('compose', '-f', 'docker-compose.yml')
$lanCompose = $base + @('-f', 'docker-compose.lan.yml')

function Invoke-CiviaDocker {
    & docker @args
    if ($LASTEXITCODE -ne 0) { throw 'Docker no pudo completar la operación. Consulta docker compose ps -a y los logs locales.' }
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Instala Docker con Docker Compose.' }
$dockerOs = docker info --format '{{.OSType}}' 2>$null
if ($LASTEXITCODE -ne 0 -or $dockerOs -ne 'linux') { throw 'Inicia Docker con contenedores Linux.' }
Invoke-CiviaDocker compose version --short | Out-Null
if (Test-Path -LiteralPath $discoveryToken) { Remove-Item -LiteralPath $discoveryToken }
if ($Stop) {
    if (-not (Test-Path -LiteralPath .env)) { Write-Host 'No hay una instalación configurada.'; return }
    Invoke-CiviaDocker @base down --remove-orphans
    return
}

if (-not (Test-Path -LiteralPath $state)) { [void](New-Item -ItemType Directory -Path $state) }
Protect-CiviaPath $state
if (-not (Test-Path -LiteralPath $accessState)) { [void](New-Item -ItemType Directory -Path $accessState) }
if (Get-Command git -ErrorAction SilentlyContinue) {
    $commit = git rev-parse --verify HEAD 2>$null
    if ($LASTEXITCODE -eq 0 -and $commit -match '^[a-f0-9]{40}$') {
        $env:CIVIA_BUILD_SHA = $commit
        if (git status --porcelain) { $env:CIVIA_BUILD_SHA += '-dirty' }
    }
}
if (-not $env:CIVIA_BUILD_SHA) { $env:CIVIA_BUILD_SHA = 'unknown' }

$apiPort = Get-CiviaPort CIVIA_API_PORT 8000
$httpPort = Get-CiviaPort CIVIA_HTTP_PORT 5173
if ($apiPort -eq $httpPort) { throw 'CIVIA_API_PORT y CIVIA_HTTP_PORT deben ser distintos.' }
$reconcileNetwork = Assert-CiviaNetwork
Assert-CiviaPort api '127.0.0.1' $apiPort 8000
Assert-CiviaPort frontend '127.0.0.1' $httpPort 80
if ($Lan) {
    $interface = Get-CiviaLanInterface $LanAddress
    $LanAddress = $interface.IPAddress
    $httpsPort = Get-CiviaPort CIVIA_HTTPS_PORT 5443
    Assert-CiviaPort frontend $LanAddress $httpsPort 443
    $env:CIVIA_LAN_ADDRESS = $LanAddress
    if (-not (Test-Path -LiteralPath $lanState)) { [void](New-Item -ItemType Directory -Path $lanState) }
}

if ($reconcileNetwork) {
    Write-Host 'Actualizando la red de CIVIA. Los volúmenes y las credenciales se conservan.'
    Invoke-CiviaDocker @base down --remove-orphans
}

Invoke-CiviaDocker @base up --build -d --wait --wait-timeout 180 api worker
Invoke-CiviaDocker @base run --rm --no-deps -T --volume "${accessState}:/bootstrap" api python -m app.bootstrap_admins --automatic --credentials-file /bootstrap/admin-access.json
$api = "http://127.0.0.1:$apiPort"
$site = "http://127.0.0.1:$httpPort"
$meta = Invoke-RestMethod -Uri "$api/api/meta" -TimeoutSec 8
if ($meta.protocol -ne 1 -or -not $meta.installation_id) { throw 'La API no confirmó la identidad de la instalación.' }

if ($Lan) {
    $prepare = @('prepare', $LanAddress, "$httpsPort", $meta.installation_id)
    if ($LanName) { $prepare += $LanName }
    Invoke-CiviaDocker @lanCompose run --build --rm --no-deps -T lan-tools @prepare
    Invoke-CiviaDocker @lanCompose up --build -d --no-deps --wait --wait-timeout 90 frontend
    $tlsName = (Get-Content -Raw -LiteralPath (Join-Path $lanState 'tls-name')).Trim()
    $ca = Join-Path $lanState 'ca.crt'
    $https = "https://${tlsName}:${httpsPort}"
    # The offline development CA publishes no CRL. Keep certificate and hostname checks enabled.
    $lanMeta = curl.exe -q --ssl-revoke-best-effort --noproxy '*' --silent --show-error --fail --max-time 8 --cacert $ca --resolve "${tlsName}:${httpsPort}:${LanAddress}" "$https/api/meta" | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0 -or $lanMeta.installation_id -ne $meta.installation_id) { throw 'El gateway HTTPS no confirmó la identidad de la instalación.' }
    $discovery = 'omitido'
    if (-not $NoDiscovery) {
        $token = [Guid]::NewGuid().ToString()
        $statusFile = Join-Path $lanState 'mdns.status'
        Set-Content -LiteralPath $statusFile -Value 'starting' -Encoding Ascii
        Set-Content -LiteralPath $discoveryToken -Value $token -Encoding Ascii
        $advertiser = Join-Path $PSScriptRoot 'lan/announce.ps1'
        $command = @('-NoProfile', '-NonInteractive', '-File', ('"' + $advertiser + '"'), '-Address', $LanAddress,
            '-InterfaceIndex', "$($interface.InterfaceIndex)", '-Port', "$httpsPort", '-TlsName', $tlsName,
            '-Installation', $meta.installation_id, '-Token', $token)
        $edition = if ($PSVersionTable.PSEdition -eq 'Core') { 'pwsh.exe' } else { 'powershell.exe' }
        $powershell = Join-Path $PSHOME $edition
        $publisher = Start-Process -FilePath $powershell -ArgumentList $command -WindowStyle Hidden -PassThru
        for ($attempt = 0; $attempt -lt 12; $attempt++) {
            $status = (Get-Content -Raw -LiteralPath $statusFile).Trim()
            if ($status -ne 'starting' -or $publisher.HasExited) { break }
            Start-Sleep -Seconds 1
        }
        $discovery = if ($status -eq 'published') { 'registrado en Windows' } elseif ($status -eq 'starting' -and -not $publisher.HasExited) { 'en inicio' } else { 'no disponible' }
    }
    Write-Host "Gateway HTTPS LAN          $https/ ($LanAddress)"
    Write-Host "Descubrimiento LAN         _civia._tcp.local. ($discovery)"
    Write-Host 'Emparejamiento Android     .civia/lan/pairing.svg o pairing.txt'
    Write-Host 'CA para PWA LAN            .civia/lan/ca.crt'
} else {
    Invoke-CiviaDocker @base up --build -d --no-deps --wait --wait-timeout 90 frontend
}

foreach ($origin in @($api, $site)) {
    $health = Invoke-RestMethod -Uri "$origin/health" -TimeoutSec 8
    if ($health.status -ne 'ok') { throw "El servicio $origin no confirmó el arranque." }
}
foreach ($url in @("$api/docs", "$api/openapi.json", "$site/", "$site/app/", "$site/admin/")) {
    $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 8
    if ($response.StatusCode -ne 200) { throw "No se pudo verificar $url." }
}
$frontendBuild = Invoke-RestMethod -Uri "$site/build.json" -TimeoutSec 8
if ($frontendBuild.commit -cne $meta.commit -or $frontendBuild.version -cne $meta.version) { throw 'El gateway y la API sirven builds distintos.' }

Invoke-CiviaDocker @base ps db api worker frontend
Invoke-CiviaDocker @base exec -T api python -m app.validate_providers
Invoke-CiviaDocker @base exec -T api python -m app.bootstrap_admins --status
Write-Host "Versión activa              $($meta.version) / $($meta.commit)"
Write-Host "Web ciudadana               $site/"
Write-Host "PWA ciudadana               $site/app/"
Write-Host "Portal administrativo      $site/admin/"
Write-Host "Swagger                    $api/docs"
if (Test-Path -LiteralPath (Join-Path $accessState 'admin-access.json')) {
    Write-Host 'Credenciales iniciales     .civia/access/admin-access.json (abre en privado)'
}
Write-Host 'Claves de IA               .\scripts\setup_ai_keys.ps1'
