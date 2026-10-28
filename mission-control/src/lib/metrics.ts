import type { MetricPoint, PrometheusResponse } from './types'

export interface EnvironmentQueries {
  cpu: string
  memory: string
  p95: string
  errorRate: string
}

function promEscape(value: string): string {
  return value.replace(/\\/g, '\\\\').replace(/"/g, '\\"')
}

/**
 * PromQL used by the environment charts. The orchestrator proxies the query to
 * Prometheus; Mission Control never talks to Prometheus directly.
 *
 * - CPU/memory use the stable Compose project label (contract §1).
 * - HTTP metrics use the Traefik service naming convention `<project>-<stage>-<service>`.
 */
export function buildEnvironmentQueries(project: string, stage: string): EnvironmentQueries {
  const composeProject = promEscape(`core-${project}-${stage}`)
  const service = promEscape(`${project}-${stage}`)
  return {
    cpu: `sum(rate(container_cpu_usage_seconds_total{container_label_com_docker_compose_project="${composeProject}"}[2m]))`,
    memory: `sum(container_memory_working_set_bytes{container_label_com_docker_compose_project="${composeProject}"})`,
    p95: `histogram_quantile(0.95, sum(rate(traefik_service_request_duration_seconds_bucket{service=~"${service}-.*"}[5m])) by (le))`,
    // `or vector(0)` keeps the chart at zero instead of "waiting" when there
    // are no 5xx series at all.
    errorRate: `sum(rate(traefik_service_requests_total{service=~"${service}-.*",code=~"5.."}[5m])) or vector(0)`,
  }
}

export const HOST_QUERIES = {
  cpu: '100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)',
  memory: '100 * (1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes))',
  disk: '100 * (1 - (max(node_filesystem_avail_bytes{mountpoint="/",fstype!~"tmpfs|overlay"}) / max(node_filesystem_size_bytes{mountpoint="/",fstype!~"tmpfs|overlay"})))',
} as const

function timestampToMillis(value: number): number {
  // Prometheus returns seconds; tolerate millisecond payloads from mocks/proxies.
  return value > 1e12 ? value : value * 1000
}

function parseSampleValue(value: unknown): number | null {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null
  if (typeof value !== 'string') return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

/**
 * Flattens a Prometheus vector/matrix response into chart points. When a query
 * returns several series (for example one per container), values at the same
 * timestamp are summed — our queries aggregate with `sum` upstream as well.
 */
export function extractMetricPoints(payload: unknown): MetricPoint[] {
  if (typeof payload !== 'object' || payload === null) return []
  const response = payload as PrometheusResponse
  const result = response.data?.result
  if (!Array.isArray(result)) return []

  const byTimestamp = new Map<number, number>()

  for (const sample of result) {
    if (!sample || typeof sample !== 'object') continue
    if (Array.isArray(sample.values)) {
      for (const pair of sample.values) {
        if (!Array.isArray(pair) || pair.length < 2) continue
        const [rawTimestamp, rawValue] = pair
        const timestamp = timestampToMillis(Number(rawTimestamp))
        const value = parseSampleValue(rawValue)
        if (!Number.isFinite(timestamp) || value === null) continue
        byTimestamp.set(timestamp, (byTimestamp.get(timestamp) ?? 0) + value)
      }
    } else if (Array.isArray(sample.value) && sample.value.length >= 2) {
      const [rawTimestamp, rawValue] = sample.value
      const timestamp = timestampToMillis(Number(rawTimestamp))
      const value = parseSampleValue(rawValue)
      if (!Number.isFinite(timestamp) || value === null) continue
      byTimestamp.set(timestamp, (byTimestamp.get(timestamp) ?? 0) + value)
    }
  }

  return [...byTimestamp.entries()]
    .map(([timestamp, value]) => ({ timestamp, value }))
    .sort((a, b) => a.timestamp - b.timestamp)
}

export function latestMetricValue(payload: unknown): number | null {
  const points = extractMetricPoints(payload)
  const last = points[points.length - 1]
  return last ? last.value : null
}

/** Merges new samples into a bounded, ascending, deduplicated history. */
export function mergeHistory(
  previous: MetricPoint[],
  incoming: MetricPoint[],
  maxPoints = 60,
): MetricPoint[] {
  if (incoming.length === 0) return previous.slice(-maxPoints)
  const merged = new Map<number, number>()
  for (const point of previous) merged.set(point.timestamp, point.value)
  for (const point of incoming) merged.set(point.timestamp, point.value)
  return [...merged.entries()]
    .map(([timestamp, value]) => ({ timestamp, value }))
    .sort((a, b) => a.timestamp - b.timestamp)
    .slice(-maxPoints)
}

/**
 * Reads a status gauge that may be a percentage or a raw 0–1 ratio and
 * normalizes it to 0–100.
 */
export function normalizePercent(value: number | null): number | null {
  if (value === null || !Number.isFinite(value)) return null
  if (value >= 0 && value <= 1) return value * 100
  return Math.min(100, Math.max(0, value))
}
