#!/usr/bin/env bash
# Core Odoo environment entrypoint.
#
# Runs as the `odoo` user from the official image. On the first boot it waits
# for PostgreSQL and initialises the database with the project modules. On
# later boots it starts Odoo and only passes -i when a requested module is
# missing (for example after a new addon was mounted).
set -euo pipefail

: "${POSTGRES_HOST:=db}"
: "${POSTGRES_USER:=odoo}"
: "${POSTGRES_DB:?POSTGRES_DB is required}"
: "${ODOO_DB:=$POSTGRES_DB}"
: "${ODOO_INIT_MODULES:=}"
: "${ODOO_DEMO:=0}"
: "${CORE_WORKERS:=0}"
: "${ODOO_CONF:=/etc/odoo/odoo.conf}"

log() {
    printf '[entrypoint] %s\n' "$*"
}

postgres_ready() {
    if command -v pg_isready >/dev/null 2>&1; then
        pg_isready -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d postgres -q
        return
    fi
    python3 - "$POSTGRES_HOST" "$POSTGRES_USER" "${POSTGRES_PASSWORD:-}" <<'PY'
import sys

import psycopg2

host, user, password = sys.argv[1:4]
psycopg2.connect(host=host, user=user, password=password, dbname="postgres").close()
PY
}

wait_for_postgres() {
    local attempt
    for attempt in $(seq 1 60); do
        if postgres_ready; then
            return 0
        fi
        log "waiting for PostgreSQL at ${POSTGRES_HOST} (${attempt}/60)"
        sleep 2
    done
    log "PostgreSQL did not become ready in time" >&2
    return 1
}

# Returns a scalar from a database. Uses psql when available (the official Odoo
# image ships postgresql-client) and falls back to psycopg2 otherwise.
db_scalar() {
    local database="$1"
    local sql="$2"
    if command -v psql >/dev/null 2>&1; then
        PGPASSWORD="${POSTGRES_PASSWORD:-}" \
            psql -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d "$database" -tAc "$sql" 2>/dev/null || true
        return
    fi
    python3 - "$POSTGRES_HOST" "$POSTGRES_USER" "${POSTGRES_PASSWORD:-}" "$database" "$sql" <<'PY' 2>/dev/null || true
import sys

import psycopg2

host, user, password, database, sql = sys.argv[1:6]
connection = psycopg2.connect(host=host, user=user, password=password, dbname=database)
connection.autocommit = True
with connection.cursor() as cursor:
    cursor.execute(sql)
    row = cursor.fetchone()
print(row[0] if row else "")
PY
}

database_initialised() {
    local exists value
    exists="$(db_scalar postgres "SELECT 1 FROM pg_database WHERE datname = '${ODOO_DB}' LIMIT 1")"
    [ "$exists" = "1" ] || return 1
    value="$(db_scalar "$ODOO_DB" "SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'ir_module_module' LIMIT 1")"
    [ "$value" = "1" ]
}

module_installed() {
    local module="$1"
    local value
    value="$(db_scalar "$ODOO_DB" "SELECT 1 FROM ir_module_module WHERE name = '${module}' AND state = 'installed' LIMIT 1")"
    [ "$value" = "1" ]
}

missing_modules() {
    local module
    for module in ${ODOO_INIT_MODULES//,/ }; do
        if ! module_installed "$module"; then
            printf '%s ' "$module"
        fi
    done
}

main() {
    # The image CMD is `odoo`; drop it so it is not passed twice.
    if [ "${1:-}" = "odoo" ]; then
        shift
    fi

    wait_for_postgres

    local init_modules=""
    if ! database_initialised; then
        init_modules="$ODOO_INIT_MODULES"
        [ -n "$init_modules" ] || init_modules="base"
        log "database ${ODOO_DB} is empty; initialising"
    elif [ -n "$ODOO_INIT_MODULES" ]; then
        init_modules="$(missing_modules)"
        init_modules="${init_modules% }"
    fi

    local args=(-c "$ODOO_CONF" -d "$ODOO_DB" --workers="$CORE_WORKERS")

    if [ -n "$init_modules" ]; then
        log "installing modules: ${init_modules}"
        args+=(-i "${init_modules// /,}")
        if [ "$ODOO_DEMO" != "1" ]; then
            args+=(--without-demo=True)
        fi
    fi

    log "starting Odoo (db=${ODOO_DB}, workers=${CORE_WORKERS})"
    exec odoo "${args[@]}" "$@"
}

main "$@"
