#!/usr/bin/env bash

civia_fail() { printf '%s\n' "CIVIA: $*" >&2; exit 1; }

civia_require_docker() {
    command -v docker >/dev/null || civia_fail 'Instala Docker con Docker Compose.'
    [[ "$(docker info --format '{{.OSType}}' 2>/dev/null)" == linux ]] || civia_fail 'Inicia Docker con contenedores Linux.'
    docker compose version --short >/dev/null || civia_fail 'Habilita Docker Compose.'
}

civia_setting() {
    local value=${!1:-}
    if [[ -z "$value" ]]; then value=$(civia_read_setting "$1"); fi
    printf '%s\n' "${value:-$2}"
}

civia_port() {
    local value
    value=$(civia_setting "$1" "$2")
    if [[ ! "$value" =~ ^[0-9]{1,5}$ ]] || ((10#$value < 1 || 10#$value > 65535)); then
        civia_fail "Configura $1 con un puerto entre 1 y 65535."
    fi
    printf '%s\n' "$((10#$value))"
}

civia_port_check() {
    local service=$1 address=$2 port=$3 target=$4 container mapping
    container=$("${base[@]}" ps -q "$service")
    if [[ -n "$container" ]]; then
        mapping=$(docker port "$container" "$target/tcp" 2>/dev/null || :)
        if grep -Fxq -e "$address:$port" -e "0.0.0.0:$port" -e "[::]:$port" <<<"$mapping"; then return; fi
    fi
    if (: >"/dev/tcp/$address/$port") 2>/dev/null; then
        civia_fail "El puerto $port no está disponible en $address. Libéralo o configura otro puerto de CIVIA."
    fi
}

civia_ipv4_range() {
    local octet a b c d length number span first
    IFS='./' read -r a b c d length <<<"$1"
    [[ "$1" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}/[0-9]{1,2}$ ]] || return 1
    for octet in "$a" "$b" "$c" "$d"; do ((10#$octet <= 255)) || return 1; done
    ((10#$length <= 32)) || return 1
    number=$(((10#$a << 24) | (10#$b << 16) | (10#$c << 8) | 10#$d))
    span=$((1 << (32 - 10#$length)))
    first=$((number / span * span))
    printf '%s %s\n' "$first" "$((first + span - 1))"
}

civia_network_check() {
    local name project subnet gateway pool limits first last networks network ranges range peer_first peer_last
    local details owner label driver ipam
    civia_reconcile_network=0
    name=$(basename "$PWD" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9_-')
    project=$(civia_setting COMPOSE_PROJECT_NAME "$name")
    subnet=$(civia_setting CIVIA_SUBNET 172.28.0.0/16)
    gateway=$(civia_setting CIVIA_GATEWAY 172.28.0.1)
    pool=$(civia_setting CIVIA_DYNAMIC_RANGE 172.28.1.0/24)
    limits=$(civia_ipv4_range "$subnet") || civia_fail 'Configura CIVIA_SUBNET con un CIDR IPv4 válido.'
    read -r first last <<<"$limits"
    networks=$(docker network ls --format '{{.Name}}')
    while read -r network; do
        [[ -n "$network" ]] || continue
        if [[ "$network" == "${project}_civia_net" ]]; then
            details=$(docker network inspect --format '{{index .Labels "com.docker.compose.project"}}|{{index .Labels "com.docker.compose.network"}}|{{.Driver}}|{{range .IPAM.Config}}{{.Subnet}}~{{.Gateway}}~{{.IPRange}};{{end}}' "$network")
            IFS='|' read -r owner label driver ipam <<<"$details"
            if [[ "$owner" != "$project" || "$label" != civia_net || "$driver" != bridge ]]; then
                civia_fail "La red $network existe y no pertenece al proyecto Compose de CIVIA. Usa un nombre de proyecto distinto."
            fi
            if [[ "$ipam" != "$subnet~$gateway~$pool;" ]]; then civia_reconcile_network=1; fi
            continue
        fi
        ranges=$(docker network inspect --format '{{range .IPAM.Config}}{{println .Subnet}}{{end}}' "$network") || continue
        while read -r range; do
            limits=$(civia_ipv4_range "$range") || continue
            read -r peer_first peer_last <<<"$limits"
            if ((first <= peer_last && peer_first <= last)); then
                civia_fail "La red $subnet se superpone con la red Docker $network ($range). Configura un bloque CIVIA libre en .env."
            fi
        done <<<"$ranges"
    done <<<"$networks"
}

civia_lan_address() {
    local requested=$1 active device choices selected
    case $(uname -s) in
        Linux)
            command -v ip >/dev/null || civia_fail 'El modo LAN necesita la herramienta ip del sistema.'
            if [[ -z "$requested" ]]; then
                device=$(ip -4 route show default | awk 'NR == 1 {for (i=1; i<NF; i++) if ($i == "dev") print $(i+1)}')
                choices=$(ip -o -4 addr show dev "$device" scope global | awk '{sub(/\/.*/,"",$4); print $4}')
            else
                choices=$(ip -o -4 addr show up scope global | awk '$2 !~ /^(docker|veth|br-|virbr|tun|tap|wg)/ {sub(/\/.*/,"",$4); print $4}')
            fi
            ;;
        Darwin)
            if [[ -z "$requested" ]]; then
                device=$(route -n get default | awk '/interface:/ {print $2}')
                choices=$(ifconfig "$device" | awk '/^[[:space:]]+inet / {print $2}')
            else
                choices=$(ifconfig -l | tr ' ' '\n' | awk '/^en[0-9]+$/' | while read -r device; do
                    ifconfig "$device" | awk '/^[[:space:]]+inet / {print $2}'
                done)
            fi
            ;;
        *) civia_fail 'Usa PowerShell en Windows para el modo LAN.' ;;
    esac
    active=$(printf '%s\n' "$choices" | awk '/^(10\.|172\.(1[6-9]|2[0-9]|3[01])\.|192\.168\.)/')
    selected=$active
    if [[ -n "$requested" ]]; then selected=$(printf '%s\n' "$active" | grep -Fx "$requested" || :); fi
    [[ -n "$selected" && "$selected" != *$'\n'* ]] || civia_fail 'Selecciona una IPv4 privada de un adaptador LAN activo con --lan-address.'
    printf '%s\n' "$selected"
}

civia_curl() {
    if command -v curl >/dev/null; then
        curl -q --noproxy '*' --fail --silent --show-error --max-time 8 "$@"
        return
    fi
    local url=$1 line result port path
    [[ "$#" -eq 1 && "$url" =~ ^http://127\.0\.0\.1:([0-9]+)(/.*)$ ]] || civia_fail 'CIVIA HTTPS requiere el cliente curl del sistema.'
    port=${BASH_REMATCH[1]}
    path=${BASH_REMATCH[2]}
    (
        exec 3<>"/dev/tcp/127.0.0.1/$port"
        printf 'GET %s HTTP/1.0\r\nHost: 127.0.0.1:%s\r\nConnection: close\r\n\r\n' "$path" "$port" >&3
        IFS= read -r -t 8 result <&3 && [[ "$result" =~ ^HTTP/[0-9.]+\ 200\  ]] || exit 1
        while IFS= read -r -t 8 line <&3 && [[ "$line" != $'\r' ]]; do :; done
        cat <&3
    )
}

civia_json_field() {
    printf '%s\n' "$1" | sed -nE "s/^.*\"$2\"[[:space:]]*:[[:space:]]*\"([^\"]+)\".*$/\1/p"
}
