import type {
  AuditEvent,
  Environment,
  Iteration,
  IterationDiff,
  LoginResponse,
  MeResponse,
  Project,
  ProjectMember,
  Stage,
  StatusPayload,
  User,
  UserRole,
} from './types'

/**
 * Mission Control's only network dependency. Everything goes through the
 * orchestrator (contract §5): no direct Docker, Prometheus or Loki calls.
 */
export const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, '') || '/api/v1'

const TOKEN_KEY = 'core-odoo.mission-control.token'
const UNAUTHORIZED_EVENT = 'core-odoo:unauthorized'

let memoryToken: string | null = null
let tokenLoaded = false
const unauthorizedHandlers = new Set<() => void>()

export class ApiError extends Error {
  readonly status: number
  readonly code?: string
  readonly details?: unknown

  constructor(message: string, status: number, code?: string, details?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
  }
}

function readStoredToken(): string | null {
  try {
    return window.localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

function writeStoredToken(token: string | null): void {
  try {
    if (token === null) window.localStorage.removeItem(TOKEN_KEY)
    else window.localStorage.setItem(TOKEN_KEY, token)
  } catch {
    // Storage can be unavailable (private mode / restricted webview).
  }
}

export function getToken(): string | null {
  if (!tokenLoaded) {
    memoryToken = readStoredToken()
    tokenLoaded = true
  }
  return memoryToken
}

export function setToken(token: string): void {
  memoryToken = token
  tokenLoaded = true
  writeStoredToken(token)
}

export function clearToken(): void {
  memoryToken = null
  tokenLoaded = true
  writeStoredToken(null)
}

/** Registers a callback invoked after a 401 response clears the session. */
export function subscribeUnauthorized(handler: () => void): () => void {
  unauthorizedHandlers.add(handler)
  return () => unauthorizedHandlers.delete(handler)
}

function handleUnauthorized(): void {
  clearToken()
  for (const handler of unauthorizedHandlers) {
    try {
      handler()
    } catch (error) {
      console.error('Unauthorized handler failed', error)
    }
  }
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent(UNAUTHORIZED_EVENT))
  }
}

export const unauthorizedEventName = UNAUTHORIZED_EVENT

type QueryValue = string | number | boolean | null | undefined

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE'
  body?: unknown
  query?: Record<string, QueryValue>
  auth?: boolean
  signal?: AbortSignal
}

export function buildUrl(
  base: string,
  path: string,
  query?: Record<string, QueryValue>,
): string {
  const url = `${base}${path}`
  if (!query) return url
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === '') continue
    params.set(key, String(value))
  }
  const qs = params.toString()
  return qs ? `${url}?${qs}` : url
}

interface ErrorPayload {
  message: string
  code?: string
  details?: unknown
}

async function parseErrorPayload(response: Response): Promise<ErrorPayload> {
  let text = ''
  try {
    text = await response.text()
  } catch {
    return { message: `HTTP ${response.status}` }
  }
  if (!text) return { message: `HTTP ${response.status}` }
  try {
    const parsed: unknown = JSON.parse(text)
    if (parsed && typeof parsed === 'object') {
      const record = parsed as Record<string, unknown>
      const nested = record.error
      if (nested && typeof nested === 'object') {
        const error = nested as Record<string, unknown>
        const message = typeof error.message === 'string' ? error.message : `HTTP ${response.status}`
        return {
          message,
          code: typeof error.code === 'string' ? error.code : undefined,
          details: error.details,
        }
      }
      if (typeof record.detail === 'string') {
        return {
          message: record.detail,
          code: typeof record.code === 'string' ? record.code : undefined,
        }
      }
      if (typeof record.message === 'string') {
        return {
          message: record.message,
          code: typeof record.code === 'string' ? record.code : undefined,
          details: record.details,
        }
      }
    }
  } catch {
    // Plain-text error body: fall through and use it as the message.
  }
  return { message: text.slice(0, 300) }
}

function isAbortError(error: unknown): boolean {
  return (
    typeof error === 'object' &&
    error !== null &&
    'name' in error &&
    (error as { name?: unknown }).name === 'AbortError'
  )
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, query, auth = true, signal } = options
  const headers = new Headers({ Accept: 'application/json' })
  const token = auth ? getToken() : null
  if (token) headers.set('Authorization', `Bearer ${token}`)

  let payload: BodyInit | undefined
  if (body !== undefined) {
    headers.set('Content-Type', 'application/json')
    payload = JSON.stringify(body)
  }

  let response: Response
  try {
    response = await fetch(buildUrl(API_BASE, path, query), {
      method,
      headers,
      body: payload,
      signal,
    })
  } catch (error) {
    if (isAbortError(error)) throw error
    throw new ApiError('', 0, 'network')
  }

  if (!response.ok) {
    const payloadInfo = await parseErrorPayload(response)
    if (response.status === 401 && auth) handleUnauthorized()
    throw new ApiError(payloadInfo.message, response.status, payloadInfo.code, payloadInfo.details)
  }

  if (response.status === 204) return undefined as T
  const text = await response.text()
  if (text === '') return undefined as T
  try {
    return JSON.parse(text) as T
  } catch {
    return text as T
  }
}

export interface CreateProjectInput {
  name: string
  template: string
  repo_url?: string
}

export interface DeployInput {
  stage: Stage
  branch?: string
  modules?: string[]
  iteration?: string
  confirm?: string
}

export interface CreateUserInput {
  username: string
  password: string
  role: UserRole
}

export interface UpdateUserInput {
  password?: string
  role?: UserRole
  active?: boolean
}

export interface CreateIterationInput {
  version: string
  title: string
  notes?: string
  branch?: string
  commit_sha?: string
  modules?: string[]
}

function projectPath(name: string): string {
  return `/projects/${encodeURIComponent(name)}`
}

function environmentPath(name: string, stage: string): string {
  return `${projectPath(name)}/environments/${encodeURIComponent(stage)}`
}

export const api = {
  auth: {
    login(username: string, password: string): Promise<LoginResponse> {
      return request<LoginResponse>('/auth/login', {
        method: 'POST',
        body: { username, password },
        auth: false,
      })
    },
    me(): Promise<MeResponse> {
      return request<MeResponse>('/auth/me')
    },
  },
  health(): Promise<{ status: string; version?: string }> {
    return request('/health', { auth: false })
  },
  status(): Promise<StatusPayload> {
    return request<StatusPayload>('/status')
  },
  projects: {
    list(): Promise<Project[]> {
      return request<Project[]>('/projects')
    },
    get(name: string): Promise<Project> {
      return request<Project>(projectPath(name))
    },
    create(input: CreateProjectInput): Promise<Project> {
      return request<Project>('/projects', { method: 'POST', body: input })
    },
    remove(name: string): Promise<{ deleted: boolean }> {
      return request(projectPath(name), { method: 'DELETE' })
    },
  },
  members: {
    list(name: string): Promise<ProjectMember[]> {
      return request<ProjectMember[]>(`${projectPath(name)}/members`)
    },
    add(name: string, username: string): Promise<ProjectMember> {
      return request<ProjectMember>(`${projectPath(name)}/members`, {
        method: 'POST',
        body: { username },
      })
    },
    remove(name: string, username: string): Promise<{ deleted: boolean }> {
      return request(`${projectPath(name)}/members/${encodeURIComponent(username)}`, {
        method: 'DELETE',
      })
    },
  },
  iterations: {
    list(name: string): Promise<Iteration[]> {
      return request<Iteration[]>(`${projectPath(name)}/iterations`)
    },
    create(name: string, input: CreateIterationInput): Promise<Iteration> {
      return request<Iteration>(`${projectPath(name)}/iterations`, {
        method: 'POST',
        body: input,
      })
    },
    restore(name: string, version: string): Promise<Iteration> {
      return request<Iteration>(
        `${projectPath(name)}/iterations/${encodeURIComponent(version)}/restore`,
        { method: 'POST' },
      )
    },
    diff(name: string, version: string, against?: string): Promise<IterationDiff> {
      return request<IterationDiff>(
        `${projectPath(name)}/iterations/${encodeURIComponent(version)}/diff`,
        { query: against ? { against } : undefined },
      )
    },
    backup(name: string, version: string, stage: string): Promise<unknown> {
      return request(
        `${projectPath(name)}/iterations/${encodeURIComponent(version)}/backup`,
        { method: 'POST', query: { stage } },
      )
    },
  },
  environments: {
    list(name: string): Promise<Environment[]> {
      return request<Environment[]>(`${projectPath(name)}/environments`)
    },
    deploy(name: string, input: DeployInput): Promise<Environment> {
      return request<Environment>(`${projectPath(name)}/deploy`, {
        method: 'POST',
        body: input,
      })
    },
    start(name: string, stage: string): Promise<Environment> {
      return request<Environment>(`${environmentPath(name, stage)}/start`, { method: 'POST' })
    },
    stop(name: string, stage: string): Promise<Environment> {
      return request<Environment>(`${environmentPath(name, stage)}/stop`, { method: 'POST' })
    },
    restart(name: string, stage: string): Promise<Environment> {
      return request<Environment>(`${environmentPath(name, stage)}/restart`, { method: 'POST' })
    },
    remove(name: string, stage: string): Promise<{ deleted: boolean }> {
      return request(environmentPath(name, stage), { method: 'DELETE' })
    },
    logs(name: string, stage: string, tail = 200): Promise<{ logs: string }> {
      return request<{ logs: string }>(`${environmentPath(name, stage)}/logs`, {
        query: { tail },
      })
    },
  },
  users: {
    list(): Promise<User[]> {
      return request<User[]>('/users')
    },
    create(input: CreateUserInput): Promise<User> {
      return request<User>('/users', { method: 'POST', body: input })
    },
    update(username: string, input: UpdateUserInput): Promise<User> {
      return request<User>(`/users/${encodeURIComponent(username)}`, {
        method: 'PATCH',
        body: input,
      })
    },
  },
  metrics: {
    /** Prometheus JSON passthrough, proxied by the orchestrator. */
    query(query: string): Promise<unknown> {
      return request<unknown>('/metrics/query', { query: { query } })
    },
  },
  audit: {
    list(limit = 100): Promise<AuditEvent[]> {
      return request<AuditEvent[]>('/audit', { query: { limit } })
    },
  },
}
