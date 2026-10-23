#!/usr/bin/env bash
# Core Odoo — one-command installer.
#
#   ./install.sh [--dev] [--lang es|en] [--domain-suffix <suffix>] [--force]
#
# Generates .env with fresh secrets (never overwrites it unless --force), creates
# the data directory and starts the control plane + observability stack.
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${REPO_ROOT}/.env"
ENV_EXAMPLE="${REPO_ROOT}/.env.example"

LANG_CHOICE="es"
DEV=0
FORCE=0
DOMAIN_SUFFIX=""

usage() {
    cat <<EOF
Usage: ./install.sh [options]

  --dev                    development defaults (debug logging)
  --lang es|en             message language (default: es)
  --domain-suffix <name>   base domain, e.g. 192.168.1.50.nip.io
  --force                  overwrite an existing .env
  -h, --help               show this help
EOF
}

say() {
    local key="$1"
    shift || true
    case "${LANG_CHOICE}:${key}" in
        es:checking) printf '→ Comprobando %s...\n' "$*" ;;
        en:checking) printf '→ Checking %s...\n' "$*" ;;
        es:ok) printf '  ✓ %s disponible\n' "$*" ;;
        en:ok) printf '  ✓ %s available\n' "$*" ;;
        es:missing) printf '✗ Falta %s. Instálalo y vuelve a ejecutar.\n' "$*" >&2 ;;
        en:missing) printf '✗ %s is missing. Install it and run again.\n' "$*" >&2 ;;
        es:daemon_down) printf '✗ El daemon de Docker no responde. Arráncalo y vuelve a intentarlo.\n' >&2 ;;
        en:daemon_down) printf '✗ The Docker daemon is not responding. Start it and try again.\n' >&2 ;;
        es:bad_lang) printf '✗ Idioma no válido: %s (usa es o en).\n' "$*" >&2 ;;
        en:bad_lang) printf '✗ Invalid language: %s (use es or en).\n' "$*" >&2 ;;
        es:bad_suffix) printf '✗ Dominio no válido: %s\n' "$*" >&2 ;;
        en:bad_suffix) printf '✗ Invalid domain: %s\n' "$*" >&2 ;;
        es:env_exists) printf '→ .env ya existe; no se sobrescribe (usa --force para regenerarlo).\n' ;;
        en:env_exists) printf '→ .env already exists; not overwriting (use --force to regenerate).\n' ;;
        es:writing_env) printf '→ Generando .env con secretos aleatorios...\n' ;;
        en:writing_env) printf '→ Generating .env with random secrets...\n' ;;
        es:data_dir) printf '→ Creando directorio de datos...\n' ;;
        en:data_dir) printf '→ Creating data directory...\n' ;;
        es:starting) printf '→ Levantando la plataforma (puede tardar unos minutos)...\n' ;;
        en:starting) printf '→ Starting the platform (this may take a few minutes)...\n' ;;
        es:urls) printf '\nURLs:\n' ;;
        en:urls) printf '\nURLs:\n' ;;
        es:panel) printf '  Panel:      http://core-odoo.%s\n' "$*" ;;
        en:panel) printf '  Panel:      http://core-odoo.%s\n' "$*" ;;
        es:api) printf '  API:        http://api.core-odoo.%s\n' "$*" ;;
        en:api) printf '  API:        http://api.core-odoo.%s\n' "$*" ;;
        es:grafana) printf '  Grafana:    http://grafana.core-odoo.%s\n' "$*" ;;
        en:grafana) printf '  Grafana:    http://grafana.core-odoo.%s\n' "$*" ;;
        es:done) printf '\nListo. Ejecuta `./scripts/e2e.sh` para validar el stack.\n' ;;
        en:done) printf '\nDone. Run `./scripts/e2e.sh` to validate the stack.\n' ;;
        es:compose_missing) printf '✗ No se encontró %s.\n' "$*" >&2 ;;
        en:compose_missing) printf '✗ %s not found.\n' "$*" >&2 ;;
        *) printf '%s\n' "$key" ;;
    esac
}

random_secret() {
    openssl rand -hex 24
}

detect_host_ip() {
    local ip=""
    if command -v ip >/dev/null 2>&1; then
        ip="$(ip route get 1.1.1.1 2>/dev/null | awk '{for (i = 1; i <= NF; i++) if ($i == "src") {print $(i + 1); exit}}')"
    fi
    if [[ -z "$ip" ]] && command -v hostname >/dev/null 2>&1; then
        ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
    fi
    printf '%s' "${ip:-127.0.0.1}"
}

require_command() {
    local name="$1"
    say checking "$name"
    if ! command -v "$name" >/dev/null 2>&1; then
        say missing "$name"
        exit 1
    fi
    say ok "$name"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dev)
            DEV=1
            shift
            ;;
        --lang)
            LANG_CHOICE="${2:-}"
            shift 2
            ;;
        --lang=*)
            LANG_CHOICE="${1#*=}"
            shift
            ;;
        --domain-suffix)
            DOMAIN_SUFFIX="${2:-}"
            shift 2
            ;;
        --domain-suffix=*)
            DOMAIN_SUFFIX="${1#*=}"
            shift
            ;;
        --force)
            FORCE=1
            shift
            ;;
        -h | --help)
            usage
            exit 0
            ;;
        *)
            printf 'Unknown option: %s\n' "$1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if [[ "$LANG_CHOICE" != "es" && "$LANG_CHOICE" != "en" ]]; then
    say bad_lang "$LANG_CHOICE"
    exit 2
fi

if [[ -n "$DOMAIN_SUFFIX" && ! "$DOMAIN_SUFFIX" =~ ^[A-Za-z0-9.-]+$ ]]; then
    say bad_suffix "$DOMAIN_SUFFIX"
    exit 2
fi

if [[ ! -f "$ENV_EXAMPLE" ]]; then
    say compose_missing "$ENV_EXAMPLE"
    exit 1
fi
for file in docker-compose.yml docker-compose.observability.yml; do
    if [[ ! -f "${REPO_ROOT}/${file}" ]]; then
        say compose_missing "$file"
        exit 1
    fi
done

require_command docker
say checking "Docker Compose v2"
if ! docker compose version >/dev/null 2>&1; then
    say missing "docker compose"
    exit 1
fi
say ok "docker compose"

if ! docker info >/dev/null 2>&1; then
    say daemon_down
    exit 1
fi

require_command openssl

cd "$REPO_ROOT"

ensure_host_paths() {
    # Bind mounts are resolved by the host Docker daemon, not by the
    # orchestrator container. Keep the host-side paths in .env.
    local key value
    for pair in "CORE_HOST_DATA_DIR:data" "CORE_HOST_PROJECTS_DIR:projects" "CORE_HOST_GATEWAY_DIR:gateway"; do
        key="${pair%%:*}"
        value="${REPO_ROOT}/${pair##*:}"
        if grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
            if [[ -z "$(grep "^${key}=" "$ENV_FILE" | head -1 | cut -d= -f2-)" ]]; then
                sed -i "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
            fi
        else
            printf '%s=%s\n' "$key" "$value" >>"$ENV_FILE"
        fi
    done
}

if [[ -f "$ENV_FILE" && "$FORCE" -eq 0 ]]; then
    say env_exists
    ensure_host_paths
else
    say writing_env
    host_ip="$(detect_host_ip)"
    suffix="${DOMAIN_SUFFIX:-${host_ip}.nip.io}"

    tmp_env="$(mktemp "${TMPDIR:-/tmp}/core-odoo-env.XXXXXX")"
    trap 'rm -f "${tmp_env:-}"' EXIT

    sed \
        -e "s|^CORE_LANG=.*|CORE_LANG=${LANG_CHOICE}|" \
        -e "s|^CORE_DOMAIN_SUFFIX=.*|CORE_DOMAIN_SUFFIX=${suffix}|" \
        -e "s|^CORE_API_URL=.*|CORE_API_URL=http://api.core-odoo.${suffix}|" \
        -e "s|^CORE_ADMIN_PASSWORD=.*|CORE_ADMIN_PASSWORD=$(random_secret)|" \
        -e "s|^CORE_API_TOKEN=.*|CORE_API_TOKEN=$(random_secret)|" \
        -e "s|^CORE_JWT_SECRET=.*|CORE_JWT_SECRET=$(random_secret)|" \
        -e "s|^CORE_ODOO_MASTER_PASSWORD=.*|CORE_ODOO_MASTER_PASSWORD=$(random_secret)|" \
        -e "s|^GRAFANA_ADMIN_PASSWORD=.*|GRAFANA_ADMIN_PASSWORD=$(random_secret)|" \
        "$ENV_EXAMPLE" >"$tmp_env"

    for pair in "CORE_HOST_DATA_DIR:data" "CORE_HOST_PROJECTS_DIR:projects" "CORE_HOST_GATEWAY_DIR:gateway"; do
        key="${pair%%:*}"
        value="${REPO_ROOT}/${pair##*:}"
        if grep -q "^${key}=" "$tmp_env"; then
            sed -i "s|^${key}=.*|${key}=${value}|" "$tmp_env"
        else
            printf '%s=%s\n' "$key" "$value" >>"$tmp_env"
        fi
    done

    if [[ "$DEV" -eq 1 ]]; then
        sed -i \
            -e "s|^CORE_LOG_LEVEL=.*|CORE_LOG_LEVEL=DEBUG|" \
            "$tmp_env"
        if ! grep -q '^CORE_DEV=' "$tmp_env"; then
            {
                printf '\n# Local development defaults\n'
                printf 'CORE_DEV=1\n'
            } >>"$tmp_env"
        fi
    fi

    mv "$tmp_env" "$ENV_FILE"
    trap - EXIT
    chmod 600 "$ENV_FILE"
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

suffix="${CORE_DOMAIN_SUFFIX:-$(detect_host_ip).nip.io}"
data_dir="${CORE_DATA_DIR:-./data}"

say data_dir
mkdir -p "$data_dir"

say urls
say panel "$suffix"
say api "$suffix"
say grafana "$suffix"

say starting
docker compose -f docker-compose.yml -f docker-compose.observability.yml up -d --build

say done
