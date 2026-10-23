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

export interface Iteration {
  project: string
  version: string
  title: string
  notes: string
  status: string
  stage?: string | null
  branch?: string | null
  commit_sha?: string | null
  modules?: string[]
  has_snapshot: boolean
  created_at: string
  deployed_at?: string | null
}

export interface IterationDiff {
  project: string
  from_version?: string | null
  to_version: string
  added: string[]
  modified: string[]
  deleted: string[]
  summary: Record<string, number>
}

export interface DeploymentRequest {
  id: number
  project: string
  stage: string
  iteration: string
  reason: string
  status: string
  requested_by: string
  decided_by?: string | null
  created_at: string
  decided_at?: string | null
  deployed_at?: string | null
}

export type ProjectRole = 'owner' | 'developer' | 'viewer'

export interface ProjectMember {
  username: string
  role: ProjectRole
  user_role: UserRole
  created_at: string
}

export interface ProjectAccess {
  role: 'admin' | ProjectRole
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

export type UserRole = 'admin' | 'operator' | 'viewer'

export interface MeResponse {
  username: string
  role: UserRole
}

export interface User {
  username: string
  role: UserRole
  active: boolean
  created_at: string
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
