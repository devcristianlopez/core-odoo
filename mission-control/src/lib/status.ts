import { formatBytes } from './format'
import type { HostMetric, ParsedStatus } from './types'

export type StatusTone = 'success' | 'warning' | 'danger' | 'neutral' | 'info'

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

const RUNNING_STATUSES = new Set([
  'running',
  'active',
  'up',
  'healthy',
  'ready',
  'started',
  'online',
])

const PENDING_STATUSES = new Set([
  'starting',
  'stopping',
  'restarting',
  'deploying',
  'provisioning',
  'building',
  'pending',
  'queued',
  'created',
])

const FAILED_STATUSES = new Set([
  'failed',
  'error',
  'unhealthy',
  'crashed',
  'down',
  'exited',
  'dead',
])

export function normalizeStatusKey(value: unknown): string {
  if (typeof value !== 'string') return 'unknown'
  return value.trim().toLowerCase().replace(/[\s.]+/g, '-') || 'unknown'
}

export function isRunningStatus(value: unknown): boolean {
  return RUNNING_STATUSES.has(normalizeStatusKey(value))
}

export function statusTone(value: unknown): StatusTone {
  const key = normalizeStatusKey(value)
  if (RUNNING_STATUSES.has(key)) return 'success'
  if (PENDING_STATUSES.has(key)) return 'warning'
  if (FAILED_STATUSES.has(key)) return 'danger'
  if (key === 'stopped' || key === 'inactive' || key === 'disabled' || key === 'paused') {
    return 'neutral'
  }
  return 'neutral'
}

export function asNumber(value: unknown): number | null {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null
  if (typeof value === 'string') {
    const cleaned = value.trim().replace(/%$/, '').replace(',', '.')
    if (cleaned === '') return null
    const parsed = Number(cleaned)
    return Number.isFinite(parsed) ? parsed : null
  }
  return null
}

const BYTE_MULTIPLIERS: Record<string, number> = {
  b: 1,
  kb: 1024,
  kib: 1024,
  mb: 1024 ** 2,
  mib: 1024 ** 2,
  gb: 1024 ** 3,
  gib: 1024 ** 3,
  tb: 1024 ** 4,
  tib: 1024 ** 4,
  pb: 1024 ** 5,
  pib: 1024 ** 5,
}

/** Parses values such as `1073741824`, `"12.5 GB"` or `"512 MiB"` into bytes. */
export function parseBytes(value: unknown): number | null {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null
  if (typeof value !== 'string') return null
  const match = value.trim().match(/^([\d.,]+)\s*([a-zA-Z]+)?$/)
  if (!match) return null
  const amount = Number((match[1] ?? '').replace(',', '.'))
  if (!Number.isFinite(amount)) return null
  const unit = (match[2] ?? 'b').toLowerCase()
  const multiplier = BYTE_MULTIPLIERS[unit]
  if (multiplier === undefined) return null
  return amount * multiplier
}

function firstDefined(record: Record<string, unknown>, keys: string[]): unknown {
  for (const key of keys) {
    if (record[key] !== undefined && record[key] !== null) return record[key]
  }
  return undefined
}

const PERCENT_KEYS = [
  'percent',
  'percentage',
  'percent_used',
  'used_percent',
  'usage_percent',
  'utilization',
  'utilization_percent',
  'load',
]

const TOTAL_KEYS = ['total', 'total_bytes', 'totalBytes', 'size', 'capacity', 'limit']
const USED_KEYS = ['used', 'used_bytes', 'usedBytes', 'usage', 'consumed']
const FREE_KEYS = ['free', 'free_bytes', 'freeBytes', 'available', 'available_bytes', 'availableBytes', 'avail']

function clampPercent(value: number): number {
  return Math.min(100, Math.max(0, value))
}

function metricFromObject(record: Record<string, unknown>, language: string): HostMetric {
  let percent: number | null = null
  for (const key of PERCENT_KEYS) {
    const parsed = asNumber(record[key])
    if (parsed !== null) {
      percent = clampPercent(parsed)
      break
    }
  }

  const total = parseBytes(firstDefined(record, TOTAL_KEYS))
  let used = parseBytes(firstDefined(record, USED_KEYS))
  const free = parseBytes(firstDefined(record, FREE_KEYS))
  if (used === null && total !== null && free !== null) used = total - free
  if (percent === null && used !== null && total !== null && total > 0) {
    percent = clampPercent((used / total) * 100)
  }

  let detail: string | null = null
  if (used !== null && total !== null) {
    detail = `${formatBytes(used, language)} / ${formatBytes(total, language)}`
  } else if (used !== null) {
    detail = formatBytes(used, language)
  } else if (free !== null && total !== null) {
    detail = `${formatBytes(free, language)} / ${formatBytes(total, language)}`
  } else {
    const message = record.message ?? record.status
    if (typeof message === 'string' && message.trim() !== '') detail = message
  }

  return { percent, detail }
}

/** Normalizes the many host metric shapes a status endpoint may return. */
export function hostMetric(value: unknown, language = 'en'): HostMetric {
  if (value === null || value === undefined) return { percent: null, detail: null }
  if (typeof value === 'number') {
    return { percent: clampPercent(value), detail: null }
  }
  if (typeof value === 'string') {
    const trimmed = value.trim()
    if (trimmed.endsWith('%')) {
      const parsed = asNumber(trimmed)
      return { percent: parsed === null ? null : clampPercent(parsed), detail: null }
    }
    const bytes = parseBytes(trimmed)
    if (bytes !== null) return { percent: null, detail: formatBytes(bytes, language) }
    return { percent: null, detail: trimmed || null }
  }
  if (isRecord(value)) return metricFromObject(value, language)
  return { percent: null, detail: null }
}

function parseDocker(value: unknown): ParsedStatus['docker'] {
  if (value === null || value === undefined) return { online: null, label: null }
  if (typeof value === 'boolean') return { online: value, label: null }
  if (typeof value === 'string') {
    const normalized = value.trim()
    const lower = normalized.toLowerCase()
    const online = !/down|error|unavailable|failed|offline/.test(lower)
    return { online, label: normalized || null }
  }
  if (isRecord(value)) {
    const status = typeof value.status === 'string' ? value.status : null
    const version = typeof value.version === 'string' ? value.version : null
    const message = typeof value.message === 'string' ? value.message : null
    const error = typeof value.error === 'string' ? value.error : null
    let online: boolean | null = null
    for (const key of ['online', 'available', 'ok', 'healthy', 'running', 'connected']) {
      if (typeof value[key] === 'boolean') {
        online = value[key] as boolean
        break
      }
    }
    if (online === null && status) {
      online = !/down|error|unavailable|failed|offline/.test(status.toLowerCase())
    }
    if (online === null && error) online = false
    return { online, label: version ?? status ?? error ?? message }
  }
  return { online: null, label: null }
}

function parseVersion(value: unknown): string | null {
  if (typeof value === 'string') return value.trim() || null
  if (typeof value === 'number') return String(value)
  if (isRecord(value)) {
    for (const key of ['version', 'app_version', 'api_version', 'tag']) {
      const candidate = value[key]
      if (typeof candidate === 'string' && candidate.trim() !== '') return candidate.trim()
    }
  }
  return null
}

function countRunning(items: unknown[]): number {
  return items.reduce<number>((total, item) => {
    if (isRecord(item) && isRunningStatus(item.status)) return total + 1
    if (typeof item === 'string' && isRunningStatus(item)) return total + 1
    return total
  }, 0)
}

function parseEnvironments(value: unknown): ParsedStatus['environments'] {
  if (typeof value === 'number') return { total: value, running: null }
  if (Array.isArray(value)) return { total: value.length, running: countRunning(value) }
  if (isRecord(value)) {
    const total =
      asNumber(firstDefined(value, ['total', 'count', 'environments', 'all'])) ??
      (Array.isArray(value.items) ? value.items.length : null)
    const running = asNumber(firstDefined(value, ['running', 'active', 'up', 'started'])) ?? null
    return { total, running }
  }
  return { total: null, running: null }
}

/**
 * Converts the loosely specified `GET /status` payload into the values the
 * dashboard renders. Missing data stays `null` so the UI can fall back or show
 * an explicit "not reported" state.
 */
export function parseStatus(payload: unknown, language = 'en'): ParsedStatus {
  const record = isRecord(payload) ? payload : {}
  const environmentSource = record.environments ?? record.environment
  const environments = parseEnvironments(environmentSource)
  return {
    version: parseVersion(record.version),
    docker: parseDocker(record.docker),
    environments,
    cpu: hostMetric(record.cpu ?? record.cpu_usage, language),
    memory: hostMetric(record.memory ?? record.ram ?? record.memory_usage, language),
    disk: hostMetric(record.disk ?? record.storage, language),
  }
}

/** Localized percentage details for cards with no data are handled by the UI. */
export function metricDetail(metric: HostMetric): string | null {
  return metric.detail
}
