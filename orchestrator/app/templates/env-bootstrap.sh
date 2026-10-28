#!/usr/bin/env bash
# Provision the gateway bot user + API key once Odoo is healthy.
set -euo pipefail

mkdir -p /run/core
: "${ODOO_DB:?ODOO_DB is required}"
: "${CORE_BOOTSTRAP_INIT_TIMEOUT:=600}"
: "${POSTGRES_HOST:=db}"
: "${POSTGRES_USER:=odoo}"

# Odoo answers /web/login while it is still installing modules, so the compose
# healthcheck can pass too early. `odoo shell` then waits on the registry load
# lock and dies, which used to exhaust every attempt on the first boot of a
# heavy ERP (account, stock). Wait for the module states to settle first.
wait_for_initialization() {
    local deadline=$((SECONDS + CORE_BOOTSTRAP_INIT_TIMEOUT))
    local pending installed
    while [ "$SECONDS" -lt "$deadline" ]; do
        pending="$(PGPASSWORD="${POSTGRES_PASSWORD:-}" psql -h "$POSTGRES_HOST" -U "$POSTGRES_USER" \
            -d "$ODOO_DB" -tAc \
            "SELECT count(*) FROM ir_module_module WHERE state IN ('to install','to upgrade','to remove')" \
            2>/dev/null || true)"
        installed="$(PGPASSWORD="${POSTGRES_PASSWORD:-}" psql -h "$POSTGRES_HOST" -U "$POSTGRES_USER" \
            -d "$ODOO_DB" -tAc \
            "SELECT count(*) FROM ir_module_module WHERE state = 'installed'" \
            2>/dev/null || true)"
        if [ "$pending" = "0" ] && [ -n "$installed" ] && [ "$installed" -gt 0 ] 2>/dev/null; then
            echo "[bootstrap] Odoo finished initialising modules"
            return 0
        fi
        echo "[bootstrap] waiting for Odoo to finish initialising modules"
        sleep 5
    done
    echo "[bootstrap] Odoo did not finish initialising in time" >&2
    return 1
}

wait_for_initialization

for attempt in $(seq 1 60); do
    if odoo shell -c /etc/odoo/odoo.conf -d "$ODOO_DB" --no-http --log-level=error \
        < /opt/core/bootstrap.py > /tmp/bootstrap.out 2>/tmp/bootstrap.err; then
        key="$(grep '^CORE_API_KEY=' /tmp/bootstrap.out | tail -1 | cut -d= -f2- || true)"
        if [ -n "$key" ]; then
            printf '%s' "$key" > /run/core/odoo_api_key
            chmod 644 /run/core/odoo_api_key
            echo "[bootstrap] API key provisioned"
            exit 0
        fi
    fi
    echo "[bootstrap] attempt ${attempt}/60 failed; retrying"
    sleep 3
done

echo "[bootstrap] could not provision the API key" >&2
cat /tmp/bootstrap.err >&2 || true
exit 1
