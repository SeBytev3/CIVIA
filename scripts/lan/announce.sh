#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")/../.."
address=$1; port=$2; name=$3; installation=$4; token=$5
state="$PWD/.civia/lan"
label="CIVIA - Servidor local ${installation:0:8}"
publisher=''
cleanup() {
    if [[ -n "$publisher" ]]; then kill "$publisher" 2>/dev/null || :; wait "$publisher" 2>/dev/null || :; fi
    publisher=''
}
trap cleanup EXIT
trap 'exit 0' INT TERM
healthy() {
    local health meta
    health=$(curl -qfs --noproxy '*' --max-time 3 --cacert "$state/ca.crt" --resolve "$name:$port:$address" "https://$name:$port/health") &&
    meta=$(curl -qfs --noproxy '*' --max-time 3 --cacert "$state/ca.crt" --resolve "$name:$port:$address" "https://$name:$port/api/meta") &&
    [[ "$health" == *'"status":"ok"'* && "$meta" == *"\"installation_id\":\"$installation\""* && "$meta" == *'"protocol":1'* ]]
}
while [[ -r "$state/mdns.token" && "$(cat "$state/mdns.token")" == "$token" ]]; do
    if healthy; then
        if [[ -z "$publisher" ]] || ! kill -0 "$publisher" 2>/dev/null; then
            cleanup
            dns-sd -P "$label" _civia._tcp local. "$port" "$name." "$address" v=1 "id=$installation" scheme=https &
            publisher=$!
        fi
    else
        cleanup
    fi
    sleep 3
done
