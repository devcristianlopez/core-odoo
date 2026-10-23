#!/usr/bin/env bash
# Provision the gateway bot user + API key once Odoo is healthy.
set -euo pipefail

mkdir -p /run/core
: "${ODOO_DB:?ODOO_DB is required}"

for attempt in $(seq 1 40); do
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
    echo "[bootstrap] attempt ${attempt}/40 failed; retrying"
    sleep 3
done

echo "[bootstrap] could not provision the API key" >&2
cat /tmp/bootstrap.err >&2 || true
exit 1
