#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")/.."
source scripts/civia-env.sh
source scripts/civia-host.sh

lan=0; stop=0; init_only=0; discovery=1; interactive=0; isolated=0; address=''; tls_name=''
while (($#)); do
    case $1 in
        --lan) lan=1; shift ;;
        --lan-address) address="${2:?Falta IPv4 LAN}"; shift 2 ;;
        --lan-name) tls_name="${2:?Falta nombre DNS}"; shift 2 ;;
        --no-discovery) discovery=0; shift ;;
        --stop) stop=1; shift ;;
        --initialize-only) init_only=1; shift ;;
        --interactive) interactive=1; shift ;;
        --isolated) isolated=1; shift ;;
        *) civia_fail "Opción no reconocida: $1" ;;
    esac
done
if ((!lan)) && [[ -n "$address$tls_name" || $discovery == 0 ]]; then civia_fail 'Usa --lan para estas opciones.'; fi
if ((stop && (lan || init_only || interactive || isolated))); then civia_fail 'Usa --stop independientemente.'; fi
if ((init_only && (interactive || isolated))); then civia_fail 'Usa --initialize-only independientemente.'; fi
if ((interactive)) && [[ ! -t 0 ]]; then civia_fail '--interactive requiere una terminal interactiva.'; fi
if ((isolated)); then
    [[ ! -e .env ]] || civia_fail '--isolated corresponde al primer arranque de un clon sin .env.'
    civia_initialize_isolated
elif ((!stop)); then
    civia_initialize_env
fi
if ((init_only)); then exit 0; fi
if ((interactive)) && { [[ -z "$(civia_read_setting GOOGLE_API_KEY_PRIMARY)" ]] || [[ -z "$(civia_read_setting GROQ_API_KEY)" ]]; }; then
    if IFS= read -r -p '¿Quieres ingresar las claves de IA ahora? [s/N] ' answer && [[ $answer =~ ^[sSyY]$ ]]; then
        ./scripts/setup_ai_keys.sh --configure-only
    fi
fi

civia_require_docker
base=(docker compose -f docker-compose.yml)
lan_compose=("${base[@]}" -f docker-compose.lan.yml)
state="$PWD/.civia"
access_state="$state/access"
lan_state="$state/lan"
rm -f -- "$lan_state/mdns.token"
if ((stop)); then
    if [[ -f .env ]]; then "${base[@]}" down --remove-orphans; fi
    exit 0
fi

mkdir -p -- "$access_state"
chmod 700 "$state" "$access_state"
if commit=$(git rev-parse --verify HEAD 2>/dev/null); then
    CIVIA_BUILD_SHA=$commit
    if [[ -n "$(git status --porcelain)" ]]; then CIVIA_BUILD_SHA+=-dirty; fi
fi
export CIVIA_BUILD_SHA="${CIVIA_BUILD_SHA:-unknown}"
export CIVIA_LAN_UID="$(id -u)" CIVIA_LAN_GID="$(id -g)"
host_user="$CIVIA_LAN_UID:$CIVIA_LAN_GID"
api_port=$(civia_port CIVIA_API_PORT 8000)
http_port=$(civia_port CIVIA_HTTP_PORT 5173)
if [[ $api_port == "$http_port" ]]; then civia_fail 'CIVIA_API_PORT y CIVIA_HTTP_PORT deben ser distintos.'; fi
civia_network_check
civia_port_check api 127.0.0.1 "$api_port" 8000
civia_port_check frontend 127.0.0.1 "$http_port" 80
if ((!lan || !discovery)); then "${lan_compose[@]}" rm -s -f lan-discovery >/dev/null; fi
if ((lan)); then
    address=$(civia_lan_address "$address")
    https_port=$(civia_port CIVIA_HTTPS_PORT 5443)
    civia_port_check frontend "$address" "$https_port" 443
    export CIVIA_LAN_ADDRESS="$address"
    mkdir -p -- "$lan_state"
    chmod 700 "$lan_state"
fi

if ((civia_reconcile_network)); then
    printf '%s\n' 'Actualizando la red de CIVIA. Los volúmenes y las credenciales se conservan.'
    "${base[@]}" down --remove-orphans
fi

"${base[@]}" up --build -d --wait --wait-timeout 180 api worker
"${base[@]}" run --rm --no-deps -T --user "$host_user" --volume "$access_state:/bootstrap" api python -m app.bootstrap_admins --automatic --credentials-file /bootstrap/admin-access.json
api="http://127.0.0.1:$api_port"
site="http://127.0.0.1:$http_port"
meta=$(civia_curl "$api/api/meta")
installation=$(civia_json_field "$meta" installation_id)
if [[ ! "$installation" =~ ^[a-f0-9-]{36}$ || "$meta" != *'"protocol":1'* ]]; then
    civia_fail 'La API no confirmó la identidad de la instalación.'
fi

if ((lan)); then
    prepare=(prepare "$address" "$https_port" "$installation")
    if [[ -n $tls_name ]]; then prepare+=("$tls_name"); fi
    "${lan_compose[@]}" run --build --rm --no-deps -T --user "$host_user" lan-tools "${prepare[@]}"
    "${lan_compose[@]}" up --build -d --no-deps --wait --wait-timeout 90 frontend
    tls_name=$(cat "$lan_state/tls-name")
    https="https://$tls_name:$https_port"
    lan_meta=$(civia_curl --cacert "$lan_state/ca.crt" --resolve "$tls_name:$https_port:$address" "$https/api/meta")
    if [[ "$(civia_json_field "$lan_meta" installation_id)" != "$installation" ]]; then
        civia_fail 'El gateway HTTPS no confirmó la identidad de la instalación.'
    fi
    status='omitido'
    if ((discovery)); then
        status='no disponible'
        docker_os=$(docker info --format '{{.OperatingSystem}}')
        if [[ $(uname -s) == Linux && $docker_os != 'Docker Desktop' ]]; then
            export CIVIA_INSTALLATION_ID="$installation" CIVIA_TLS_NAME="$tls_name"
            if "${lan_compose[@]}" up -d --no-build --no-deps lan-discovery; then status='servicio iniciado'; fi
        elif [[ $(uname -s) == Darwin ]] && command -v dns-sd >/dev/null; then
            token=$(civia_secret)
            printf '%s\n' "$token" >"$lan_state/mdns.token"
            nohup bash scripts/lan/announce.sh "$address" "$https_port" "$tls_name" "$installation" "$token" </dev/null >/dev/null 2>&1 &
            status='adaptador iniciado'
        fi
    fi
    printf '%s\n' \
        "Gateway HTTPS LAN          $https/ ($address)" \
        "Descubrimiento LAN         _civia._tcp.local. ($status)" \
        'Emparejamiento Android     .civia/lan/pairing.svg o pairing.txt' \
        'CA para PWA LAN            .civia/lan/ca.crt'
else
    "${base[@]}" up --build -d --no-deps --wait --wait-timeout 90 frontend
fi

for origin in "$api" "$site"; do
    health=$(civia_curl "$origin/health")
    [[ "$(civia_json_field "$health" status)" == ok ]] || civia_fail "El servicio $origin no confirmó el arranque."
done
for url in "$api/docs" "$api/openapi.json" "$site/" "$site/app/" "$site/admin/"; do civia_curl "$url" >/dev/null; done
build=$(civia_curl "$site/build.json")
commit=$(civia_json_field "$meta" commit)
version=$(civia_json_field "$meta" version)
if [[ "$(civia_json_field "$build" commit)" != "$commit" || "$(civia_json_field "$build" version)" != "$version" ]]; then
    civia_fail 'El gateway y la API sirven builds distintos.'
fi

"${base[@]}" ps db api worker frontend
"${base[@]}" exec -T api python -m app.validate_providers
"${base[@]}" exec -T api python -m app.bootstrap_admins --status
printf '%s\n' \
    "Versión activa              $version / $commit" \
    "Web ciudadana               $site/" \
    "PWA ciudadana               $site/app/" \
    "Portal administrativo      $site/admin/" \
    "Swagger                     $api/docs"
if [[ -f "$access_state/admin-access.json" ]]; then
    printf '%s\n' 'Credenciales iniciales     .civia/access/admin-access.json (abre en privado)'
fi
printf '%s\n' 'Claves de IA               ./scripts/setup_ai_keys.sh'
