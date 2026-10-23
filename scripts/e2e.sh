#!/usr/bin/env bash
# Core Odoo — end-to-end smoke test.
#
# Creates the disposable `smoke-test` project through the orchestrator API,
# deploys stage `dev`, exercises browser -> nginx -> gateway -> Odoo CRUD, checks
# Mission Control, deletes the project and asserts a clean Docker host.
#
# Usage: ./scripts/e2e.sh
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PROJECT="smoke-test"
STAGE="dev"
MODULES="base,smoke_test"
COMPOSE_PROJECT="core-${PROJECT}-${STAGE}"
CONTROL_COMPOSE=(docker compose -p core-odoo -f docker-compose.yml -f docker-compose.observability.yml)
LOG_DIR="${ROOT_DIR}/data/e2e"

mkdir -p "$LOG_DIR"

log() {
    printf '[e2e] %s\n' "$*"
}

dump_logs() {
    log "--- control plane: ${CONTROL_COMPOSE[*]} ---"
    "${CONTROL_COMPOSE[@]}" ps 2>/dev/null || true
    "${CONTROL_COMPOSE[@]}" logs --tail=150 2>/dev/null || true
    log "--- environment: ${COMPOSE_PROJECT} ---"
    docker compose -p "$COMPOSE_PROJECT" ps 2>/dev/null || true
    docker compose -p "$COMPOSE_PROJECT" logs --tail=250 2>/dev/null || true
}

on_error() {
    local code="$1"
    local line="$2"
    set +e
    log "FAILED at line ${line} (exit ${code})"
    local report="${LOG_DIR}/failure-$(date +%Y%m%d-%H%M%S).log"
    dump_logs >"$report" 2>&1
    log "full logs: ${report}"
    exit "$code"
}
trap 'on_error $? $LINENO' ERR

die() {
    log "ERROR: $*" >&2
    return 1
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"
}

require_command docker
require_command curl
require_command python3

if [[ ! -f "${ROOT_DIR}/.env" ]]; then
    log "no .env found; running install.sh --dev"
    "${ROOT_DIR}/install.sh" --dev
fi

set -a
# shellcheck disable=SC1091
source "${ROOT_DIR}/.env"
set +a

: "${CORE_API_TOKEN:?CORE_API_TOKEN is missing from .env}"
: "${CORE_DOMAIN_SUFFIX:?CORE_DOMAIN_SUFFIX is missing from .env}"

HOST_HEADER="${PROJECT}-${STAGE}.core-odoo.${CORE_DOMAIN_SUFFIX}"
PANEL_HOST="core-odoo.${CORE_DOMAIN_SUFFIX}"
API_HOST="api.core-odoo.${CORE_DOMAIN_SUFFIX}"

# Only Traefik publishes 80/443 on the host (contract §2). Reach the
# orchestrator API and the environment frontend through Traefik, not by port.
HOST_ADDR="http://127.0.0.1"
API_URL="${HOST_ADDR}/api/v1"
if [[ "${CORE_DATA_DIR:-}" = /* ]]; then
    DATA_DIR="$CORE_DATA_DIR"
else
    DATA_DIR="${ROOT_DIR}/${CORE_DATA_DIR:-data}"
fi
ENV_COMPOSE_FILE="${DATA_DIR}/envs/${PROJECT}-${STAGE}/docker-compose.yml"
DB_NAME="${PROJECT//-/_}_${STAGE}"

# --- HTTP helpers -------------------------------------------------------------

api_request() {
    local method="$1"
    local path="$2"
    local body="${3:-}"
    local tmp args
    tmp="$(mktemp)"
    args=(
        -sS
        -o "$tmp"
        -w '%{http_code}'
        -X "$method"
        -H "Host: ${API_HOST}"
        -H "Authorization: Bearer ${CORE_API_TOKEN}"
        -H 'Accept: application/json'
        "${API_URL}${path}"
    )
    if [[ -n "$body" ]]; then
        args+=(-H 'Content-Type: application/json' --data "$body")
    fi
    API_STATUS="$(curl "${args[@]}" 2>/dev/null || true)"
    API_BODY="$(cat "$tmp")"
    rm -f "$tmp"
    [[ "$API_STATUS" =~ ^[0-9]{3}$ ]] || API_STATUS="000"
}

env_request() {
    local method="$1"
    local path="$2"
    local body="${3:-}"
    local tmp args
    tmp="$(mktemp)"
    args=(
        -sS
        -o "$tmp"
        -w '%{http_code}'
        -X "$method"
        -H "Host: ${HOST_HEADER}"
        -H 'Accept: application/json'
        "${HOST_ADDR}${path}"
    )
    if [[ -n "$body" ]]; then
        args+=(-H 'Content-Type: application/json' --data "$body")
    fi
    API_STATUS="$(curl "${args[@]}" 2>/dev/null || true)"
    API_BODY="$(cat "$tmp")"
    rm -f "$tmp"
    [[ "$API_STATUS" =~ ^[0-9]{3}$ ]] || API_STATUS="000"
}

expect_status() {
    local label="$1"
    shift
    local status
    for status in "$@"; do
        if [[ "$API_STATUS" == "$status" ]]; then
            return 0
        fi
    done
    die "${label}: expected HTTP [$*], got ${API_STATUS}: ${API_BODY:0:400}"
}

wait_orchestrator() {
    local timeout="$1"
    local deadline=$((SECONDS + timeout))
    while ((SECONDS < deadline)); do
        if curl -fsS -H "Host: ${API_HOST}" "${HOST_ADDR}/health" >/dev/null 2>&1 \
            || curl -fsS -H "Host: ${API_HOST}" "${API_URL}/health" >/dev/null 2>&1; then
            log "orchestrator is healthy"
            return 0
        fi
        sleep 3
    done
    die "orchestrator did not become healthy within ${timeout}s"
}

# --- Docker helpers -----------------------------------------------------------

compose_container_ids() {
    docker ps -aq --filter "label=com.docker.compose.project=$1"
}

compose_service_id() {
    docker ps -q \
        --filter "label=com.docker.compose.project=$1" \
        --filter "label=com.docker.compose.service=$2" \
        | head -n 1 || true
}

container_health() {
    local id="$1"
    if [[ -z "$id" ]]; then
        printf 'missing'
        return
    fi
    docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$id" 2>/dev/null || printf 'missing'
}

environment_ready() {
    local service id state health
    for service in db odoo gateway frontend; do
        id="$(compose_service_id "$COMPOSE_PROJECT" "$service")"
        [[ -n "$id" ]] || return 1
        state="$(docker inspect -f '{{.State.Status}}' "$id" 2>/dev/null || true)"
        [[ "$state" == "running" ]] || return 1
        health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$id" 2>/dev/null || true)"
        [[ "$health" == "healthy" || "$health" == "none" ]] || return 1
    done
    id="$(compose_service_id "$COMPOSE_PROJECT" "mailpit")"
    if [[ -n "$id" ]]; then
        state="$(docker inspect -f '{{.State.Status}}' "$id" 2>/dev/null || true)"
        [[ "$state" == "running" ]] || return 1
    fi
    return 0
}

wait_for_database() {
    local timeout="$1"
    local deadline=$((SECONDS + timeout))
    local id
    while ((SECONDS < deadline)); do
        id="$(compose_service_id "$COMPOSE_PROJECT" db)"
        if [[ -n "$id" && "$(container_health "$id")" == "healthy" ]]; then
            log "database ${COMPOSE_PROJECT} is healthy"
            return 0
        fi
        sleep 3
    done
    die "database ${COMPOSE_PROJECT} did not become healthy within ${timeout}s"
}

# Install the fixture modules through the Odoo image entrypoint. This is
# idempotent: `-i` updates an already installed module in place.
ensure_modules() {
    [[ -f "$ENV_COMPOSE_FILE" ]] \
        || die "rendered compose file not found: ${ENV_COMPOSE_FILE}"

    log "ensuring Odoo modules are installed (${MODULES})"
    docker compose -p "$COMPOSE_PROJECT" -f "$ENV_COMPOSE_FILE" stop odoo >/dev/null 2>&1 || true
    docker compose -p "$COMPOSE_PROJECT" -f "$ENV_COMPOSE_FILE" run --rm --no-deps -T odoo \
        odoo --stop-after-init -c /etc/odoo/odoo.conf -d "$DB_NAME" -i "$MODULES" --without-demo=True
    docker compose -p "$COMPOSE_PROJECT" -f "$ENV_COMPOSE_FILE" up -d odoo >/dev/null
}

wait_for_environment() {
    local timeout="$1"
    local deadline=$((SECONDS + timeout))
    while ((SECONDS < deadline)); do
        if environment_ready; then
            log "environment ${COMPOSE_PROJECT} is healthy"
            return 0
        fi
        sleep 5
    done
    docker compose -p "$COMPOSE_PROJECT" ps 2>/dev/null || true
    die "environment ${COMPOSE_PROJECT} did not become healthy within ${timeout}s"
}

wait_compose_absent() {
    local project="$1"
    local timeout="$2"
    local deadline=$((SECONDS + timeout))
    while ((SECONDS < deadline)); do
        if [[ -z "$(compose_container_ids "$project")" ]]; then
            return 0
        fi
        sleep 3
    done
    die "environment ${project} still has containers after ${timeout}s"
}

leftovers() {
    {
        docker ps -a --filter "name=core-smoke-test" --format '{{.Names}}'
        docker network ls --filter "name=core-smoke-test" --format '{{.Name}}'
        docker volume ls --filter "name=core-smoke-test" --format '{{.Name}}'
    } | sed '/^$/d'
}

wait_clean() {
    local timeout="$1"
    local deadline=$((SECONDS + timeout))
    while ((SECONDS < deadline)); do
        if [[ -z "$(leftovers)" ]]; then
            log "no core-smoke-test containers, networks or volumes remain"
            return 0
        fi
        sleep 3
    done
    die "leftovers remain: $(leftovers | tr '\n' ' ')"
}

# --- 1. Control plane ---------------------------------------------------------

log "starting control plane"
"${CONTROL_COMPOSE[@]}" up -d --build

wait_orchestrator 120

# --- 2. Project ---------------------------------------------------------------

api_request GET "/projects/${PROJECT}"
case "$API_STATUS" in
    200)
        log "project ${PROJECT} already registered"
        ;;
    404)
        log "creating project ${PROJECT}"
        api_request POST "/projects" "{\"name\":\"${PROJECT}\",\"template\":\"odoo-module\"}"
        expect_status "create project" 200 201 409
        ;;
    *)
        die "get project: expected HTTP 200/404, got ${API_STATUS}: ${API_BODY:0:400}"
        ;;
esac

# --- 3. Clean previous dev environment ---------------------------------------

api_request GET "/projects/${PROJECT}/environments"
expect_status "list environments" 200

HAS_DEV=0
if printf '%s' "$API_BODY" | python3 -c '
import json
import sys

payload = json.load(sys.stdin)
rows = payload if isinstance(payload, list) else payload.get("environments", [])
raise SystemExit(0 if any(isinstance(row, dict) and row.get("stage") == "dev" for row in rows) else 1)
'; then
    HAS_DEV=1
fi

if [[ "$HAS_DEV" -eq 1 ]]; then
    log "removing previous ${STAGE} environment"
    api_request DELETE "/projects/${PROJECT}/environments/${STAGE}"
    expect_status "delete previous environment" 200 202 204
    wait_compose_absent "$COMPOSE_PROJECT" 90
fi

if [[ -n "$(compose_container_ids "$COMPOSE_PROJECT")" ]]; then
    log "removing stale compose project ${COMPOSE_PROJECT}"
    compose_container_ids "$COMPOSE_PROJECT" | xargs -r docker rm -f >/dev/null 2>&1 || true
    docker network rm "${COMPOSE_PROJECT}_default" >/dev/null 2>&1 || true
    docker volume rm \
        "${COMPOSE_PROJECT}_pgdata" \
        "${COMPOSE_PROJECT}_odoo_data" \
        "${COMPOSE_PROJECT}_filestore" \
        "${COMPOSE_PROJECT}_backups" >/dev/null 2>&1 || true
fi

# --- 4. Deploy ----------------------------------------------------------------

log "deploying ${PROJECT} to ${STAGE}"
api_request POST "/projects/${PROJECT}/deploy" "{\"stage\":\"${STAGE}\",\"modules\":[\"smoke_test\"]}"
expect_status "deploy ${STAGE}" 200 201 202

wait_for_database 180
ensure_modules
wait_for_environment 300

# --- 5. Gateway CRUD through the frontend ------------------------------------

log "waiting for gateway through the frontend"
GATEWAY_DEADLINE=$((SECONDS + 120))
while ((SECONDS < GATEWAY_DEADLINE)); do
    env_request GET "/api/contacts?limit=1"
    if [[ "$API_STATUS" == "200" ]]; then
        break
    fi
    if [[ "$API_STATUS" == "401" || "$API_STATUS" == "403" ]]; then
        die "gateway cannot authenticate to Odoo (HTTP ${API_STATUS}): ${API_BODY:0:400}"
    fi
    sleep 3
done
if [[ "$API_STATUS" != "200" ]]; then
    die "gateway unreachable via ${HOST_HEADER}: HTTP ${API_STATUS}: ${API_BODY:0:400}"
fi

log "creating contact"
env_request POST "/api/contacts" '{"name":"E2E Contact","nickname":"e2e"}'
expect_status "create contact" 200 201

CONTACT_ID="$(
    printf '%s' "$API_BODY" | python3 -c '
import json
import sys

payload = json.load(sys.stdin)


def find_id(value):
    if isinstance(value, dict):
        candidate = value.get("id")
        if isinstance(candidate, int):
            return candidate
        if isinstance(candidate, str) and candidate.isdigit():
            return int(candidate)
        for key in ("data", "result", "record"):
            if key in value:
                found = find_id(value[key])
                if found is not None:
                    return found
    if isinstance(value, list) and value:
        return find_id(value[0])
    return None


found = find_id(payload)
if found is None:
    raise SystemExit(1)
print(found)
'
)" || die "create contact: no id in response: ${API_BODY:0:400}"
log "created contact id=${CONTACT_ID}"

log "listing contacts"
env_request GET "/api/contacts?limit=100"
expect_status "list contacts" 200
if ! printf '%s' "$API_BODY" | python3 -c '
import json
import sys

target = str(sys.argv[1])
payload = json.load(sys.stdin)


def rows(value):
    if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
        return value
    if isinstance(value, dict):
        for key in ("items", "data", "records", "results"):
            if key in value:
                found = rows(value[key])
                if found:
                    return found
    return []


print("ok" if any(str(row.get("id")) == target for row in rows(payload)) else "missing")
' "$CONTACT_ID" | grep -qx 'ok'; then
    die "created contact ${CONTACT_ID} not present in list: ${API_BODY:0:400}"
fi

log "reading contact"
env_request GET "/api/contacts/${CONTACT_ID}"
expect_status "read contact" 200

log "updating contact"
env_request PATCH "/api/contacts/${CONTACT_ID}" '{"nickname":"e2e-updated"}'
expect_status "update contact" 200

env_request GET "/api/contacts/${CONTACT_ID}"
expect_status "read updated contact" 200
if ! printf '%s' "$API_BODY" | python3 -c '
import json
import sys

payload = json.load(sys.stdin)


def contains(value):
    if isinstance(value, dict):
        if value.get("nickname") == "e2e-updated":
            return True
        return any(contains(item) for item in value.values())
    if isinstance(value, list):
        return any(contains(item) for item in value)
    return False


raise SystemExit(0 if contains(payload) else 1)
'; then
    die "updated nickname not returned: ${API_BODY:0:400}"
fi

log "deleting contact"
env_request DELETE "/api/contacts/${CONTACT_ID}"
expect_status "delete contact" 200 202 204

env_request GET "/api/contacts/${CONTACT_ID}"
if [[ "$API_STATUS" != "404" ]]; then
    die "contact ${CONTACT_ID} still readable after delete (HTTP ${API_STATUS})"
fi

# --- 6. Mission Control -------------------------------------------------------

MC_STATUS="$(curl -sS -o /dev/null -w '%{http_code}' -H "Host: ${PANEL_HOST}" "${HOST_ADDR}/" 2>/dev/null || true)"
if [[ "$MC_STATUS" == "200" ]]; then
    log "Mission Control responds via Traefik (${PANEL_HOST})"
elif "${CONTROL_COMPOSE[@]}" exec -T mission-control wget -qO- http://127.0.0.1:3000/ >/dev/null 2>&1; then
    log "Mission Control responds inside the control plane (Traefik returned ${MC_STATUS})"
else
    die "Mission Control did not respond via Traefik or inside core-odoo"
fi

# --- 7. Delete and assert clean ---------------------------------------------

log "deleting project ${PROJECT}"
api_request DELETE "/projects/${PROJECT}"
expect_status "delete project" 200 202 204

wait_clean 90

log "E2E PASSED"
