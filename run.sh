#!/usr/bin/env sh
set -eu
exec bash "$(dirname -- "$0")/scripts/run.sh" "$@"
