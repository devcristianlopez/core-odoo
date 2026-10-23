# Observability

Prometheus, Loki, Alloy, Grafana, Alertmanager, Uptime Kuma, node-exporter and
cAdvisor for the Core Odoo control plane.

Everything here is an **override** file: it is always started together with the
control plane so both stacks share the `core-edge` network and Traefik.

```bash
docker compose -f docker-compose.yml -f docker-compose.observability.yml up -d
```

Memory budget: every service has a `mem_limit`; the whole file stays under
~2 GB (Prometheus 512 MB, Loki 384 MB, Grafana 256 MB, Alloy 192 MB,
Uptime Kuma 192 MB, cAdvisor 192 MB, Alertmanager 128 MB, node-exporter 64 MB).

## Access

Only Traefik publishes host ports (80/443). Observability UIs are routed by
hostname with nip.io, so no DNS setup is needed:

| UI | URL | Credentials |
|---|---|---|
| Grafana | `http://grafana.core-odoo.<CORE_DOMAIN_SUFFIX>` | `GRAFANA_ADMIN_USER` / `GRAFANA_ADMIN_PASSWORD` from `.env` |
| Uptime Kuma | `http://uptime.core-odoo.<CORE_DOMAIN_SUFFIX>` | created on first visit |
| Prometheus | internal only (`prometheus:9090` on `core-edge`) | – |
| Alertmanager | internal only (`alertmanager:9093` on `core-edge`) | – |
| Loki | internal only (`loki:3100` on `core-edge`) | – |

`CORE_DOMAIN_SUFFIX` is the value from `.env` (for example
`192.168.1.50.nip.io`). For remote testing, start the tunnel profile:

```bash
docker compose --profile tunnel up -d cloudflared
```

## Layout

```
observability/
├── prometheus/
│   ├── prometheus.yml        # scrape jobs + rule_files
│   └── alerts.yml            # alerting rules
├── loki/
│   └── config.yml            # single-binary Loki, filesystem, 336h retention
├── alloy/
│   └── config.alloy          # Docker log discovery -> Loki
├── grafana/
│   ├── provisioning/
│   │   ├── datasources/datasources.yml
│   │   └── dashboards/dashboards.yml
│   └── dashboards/
│       ├── core-overview.json
│       └── core-environment.json
└── alertmanager/
    └── alertmanager.yml
```

## Add a scrape target

1. Make sure the target is reachable from the `core-edge` network (container
   name or service alias) and exposes a Prometheus `/metrics` endpoint.
2. Add a job to `observability/prometheus/prometheus.yml`:

   ```yaml
   scrape_configs:
     - job_name: my-service
       metrics_path: /metrics
       static_configs:
         - targets:
             - my-service:9000
   ```

   Or discover every container labelled `core.metrics=true`:

   ```yaml
   scrape_configs:
     - job_name: core-labelled
       docker_sd_configs:
         - host: unix:///var/run/docker.sock
           filters:
             - name: label
               values: ["core.metrics=true"]
       relabel_configs:
         - source_labels: [__meta_docker_container_label_core_metrics_port]
           target_label: __address__
           replacement: $1
   ```

3. Reload Prometheus without restarting the stack:

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.observability.yml \
     exec prometheus wget -qO- --post-data='' http://localhost:9090/-/reload
   ```

   `--web.enable-lifecycle` is required for this; add it to the Prometheus
   `command` if you want hot reload (otherwise `docker compose restart prometheus`).

## Dashboards

- `core-overview` — host CPU/RAM/disk, number of running environments, request
  rate and 5xx rate.
- `core-environment` — per-environment CPU/RAM, p95 latency, 5xx rate and logs.
  The `Environment` variable lists Compose projects named
  `core-<project>-<dev|staging|prod>` and strips the `core-` prefix.

Provisioned dashboards live in `observability/grafana/dashboards/` and are
mounted read-only; add or edit JSON files there and Grafana reloads every 30 s.
Dashboard UIs are provisioned into the `Core Odoo` folder.

## Alerts

Rules live in `observability/prometheus/alerts.yml`:

| Alert | Severity | Signal |
|---|---|---|
| `EnvironmentDown` | critical | `up == 0` for orchestrator/Traefik |
| `HighHttp5xxRate` | warning | > 5% 5xx responses per Traefik service |
| `HighP95Latency` | warning | p95 > 2 s per Traefik service |
| `DiskAlmostFull` | critical | root filesystem > 85% |
| `BackupMissing` | critical | no successful backup in 24 h |
| `DeployFailed` | warning | failed deploy in the last 15 min |
| `OdooCronLag` | warning | Odoo cron lag > 1 h |

Alertmanager groups by `alertname` and sends to
`http://orchestrator:8080/api/v1/alerts` (log-only placeholder). Edit
`observability/alertmanager/alertmanager.yml` to plug in Slack/Teams/Discord.

## Logs

Alloy discovers every Docker container on the host and pushes stdout/stderr to
Loki. Containers created by the orchestrator carry `core.project` and
`core.stage` labels, which Alloy promotes to Loki labels:

```logql
{project="smoke-test", stage="dev"}
{container=~"core-smoke-dev-.*"}
```

Retention is 336 h (14 days) in `observability/loki/config.yml`. Loki does not
interpolate environment variables in YAML, so `LOKI_RETENTION` in `.env` is
informational only; change both places to alter retention.
