/**
 * Types mirroring the orchestrator API contract (docs/CONTRACT.md §5).
 *
 * The API is intentionally treated as untrusted input: older/newer
 * orchestrator builds may omit optional fields, so every consumer normalizes
 * the payload before rendering it.
 */

export const STAGES = ['dev', 'staging', 'prod'] as const
export type Stage = (typeof STAGES)[number]

export function isStage(value: unknown): value is Stage {
  return typeof value === 'string' && (STAGES as readonly string[]).includes(value)
}

export interface Environment {
  project: string
  stage: string
  status: string
  url: string | null
  compose_project: string
  branch?: string | null
  modules?: string[]
  /** The orchestrator may report services as a list or a map; normalize it. */
  services?: unknown
  created_at?: string | null
  updated_at?: string | null
}

export interface Project {
  name: string
  template: string
  repo_url?: string | null
  created_at?: string | null
  environments?: Environment[]
}

export interface LoginResponse {
  access_token: string
  token_type?: string
}

export interface MeResponse {
  username: string
}

export interface StatusPayload {
  docker?: unknown
  disk?: unknown
  environments?: unknown
  version?: unknown
  /** Optional host gauges; tolerated but not required by the contract. */
  cpu?: unknown
  memory?: unknown
  ram?: unknown
  [key: string]: unknown
}

export interface AuditEvent {
  id?: string | number
  ts?: string
  timestamp?: string
  time?: string
  created_at?: string
  actor?: string
  user?: string
  username?: string
  action?: string
  event?: string
  project?: string
  stage?: string
  status?: string
  message?: string
  details?: unknown
  [key: string]: unknown
}

export interface PrometheusSample {
  metric: Record<string, string>
  value?: [number, string]
  values?: Array<[number, string]>
}

export interface PrometheusResponse {
  status?: string
  data?: {
    resultType?: string
    result?: PrometheusSample[]
  }
  error?: string
  errorType?: string
}

export interface MetricPoint {
  timestamp: number
  value: number
}

export interface MetricSeries {
  label: string
  points: MetricPoint[]
}

export interface HostMetric {
  percent: number | null
  detail: string | null
}

export interface ParsedStatus {
  version: string | null
  docker: {
    online: boolean | null
    label: string | null
  }
  environments: {
    total: number | null
    running: number | null
  }
  cpu: HostMetric
  memory: HostMetric
  disk: HostMetric
}

export interface NormalizedAuditEvent {
  id: string
  timestamp: string | null
  actor: string | null
  action: string
  project: string | null
  stage: string | null
  status: string | null
  detail: string | null
}

export interface ServiceStatus {
  name: string
  status: string | null
}
