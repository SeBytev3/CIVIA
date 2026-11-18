#!/usr/bin/env bash
# Funciones compartidas por el arranque y el configurador.
civia_read_setting() {
    awk -v name="$1" '
        index($0, name "=") == 1 {
            value=substr($0, length(name)+2)
            sub(/\r$/, "", value)
            if (value ~ /^".*"$/ || value ~ /^\047.*\047$/) value=substr(value, 2, length(value)-2)
            print value
            exit
        }' .env
}

civia_write_setting() {
    local filename
    filename=$(mktemp .env.tmp.XXXXXX)
    if ! printf '%s\n' "$2" | awk -v name="$1" '
        BEGIN { getline value }
        index($0, name "=") == 1 { if (!found++) print name "=" value; next }
        { print }
        END { if (!found) print name "=" value }
    ' - .env >"$filename"; then
        rm -f -- "$filename"
        return 1
    fi
    mv -- "$filename" .env
}

civia_add_setting() {
    if [[ -z "$(civia_read_setting "$1")" ]]; then civia_write_setting "$1" "$2"; fi
}

civia_secret() {
    od -An -N32 -tx1 </dev/urandom | tr -d ' \n'
}

civia_initialize_env() {
    umask 077
    if [[ ! -f .env ]]; then cp .env.example .env; fi
    chmod 600 .env
    civia_add_setting POSTGRES_DB civia
    civia_add_setting POSTGRES_USER civia
    civia_add_setting POSTGRES_PASSWORD "$(civia_secret)"
    civia_add_setting ADMIN_TOKEN "$(civia_secret)"
    local db user password
    db=$(civia_read_setting POSTGRES_DB)
    user=$(civia_read_setting POSTGRES_USER)
    password=$(civia_read_setting POSTGRES_PASSWORD)
    if [[ ! "$db" =~ ^[a-zA-Z0-9_]+$ || ! "$user" =~ ^[a-zA-Z0-9_]+$ ]]; then
        printf '%s\n' 'Use identificadores de PostgreSQL alfanuméricos en la configuración local.' >&2
        return 1
    fi
    if [[ -z "$(civia_read_setting DATABASE_URL)" && ! "$password" =~ ^[a-zA-Z0-9_-]+$ ]]; then
        printf '%s\n' 'Configure DATABASE_URL con la contraseña existente codificada para URI.' >&2
        return 1
    fi
    civia_add_setting DATABASE_URL "postgresql://$user:$password@db:5432/$db"
    civia_add_setting APP_DATABASE_URL "postgresql://civia_app:$(civia_secret)@db:5432/$db"
    civia_add_setting AGENT_DATABASE_URL "postgresql://civia_agent:$(civia_secret)@db:5432/$db"
    civia_add_setting WORKER_DATABASE_URL "postgresql://civia_worker:$(civia_secret)@db:5432/$db"
}
