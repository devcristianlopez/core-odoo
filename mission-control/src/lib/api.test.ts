import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  ApiError,
  api,
  buildUrl,
  clearToken,
  getToken,
  setToken,
  subscribeUnauthorized,
} from './api'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function firstFetchCall(fetchMock: ReturnType<typeof vi.fn>): [string, RequestInit] {
  const call = fetchMock.mock.calls[0]
  expect(call).toBeDefined()
  const [url, init] = call as [string, RequestInit]
  return [url, init]
}

beforeEach(() => {
  window.localStorage.clear()
  clearToken()
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('buildUrl', () => {
  it('appends non-empty query parameters and skips empty values', () => {
    expect(
      buildUrl('/api/v1/audit', '/', { limit: 100, tail: undefined, empty: '', zero: 0 }),
    ).toBe('/api/v1/audit/?limit=100&zero=0')
  })

  it('encodes PromQL', () => {
    const url = buildUrl('/api/v1', '/metrics/query', {
      query: 'sum(rate(http_requests_total{code="500"}[5m]))',
    })
    expect(url).toContain('/metrics/query?query=')
    expect(new URL(url, 'http://localhost').searchParams.get('query')).toBe(
      'sum(rate(http_requests_total{code="500"}[5m]))',
    )
  })
})

describe('api client', () => {
  it('posts credentials without an Authorization header', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ access_token: 'jwt-token' }))
    vi.stubGlobal('fetch', fetchMock)

    const result = await api.auth.login('admin', 'secret')

    expect(result.access_token).toBe('jwt-token')
    const [url, init] = firstFetchCall(fetchMock)
    expect(url).toBe('/api/v1/auth/login')
    expect(init.method).toBe('POST')
    expect(new Headers(init.headers).has('Authorization')).toBe(false)
    expect(new Headers(init.headers).get('Content-Type')).toBe('application/json')
    expect(init.body).toBe(JSON.stringify({ username: 'admin', password: 'secret' }))
  })

  it('persists the token and attaches it as a bearer token', async () => {
    setToken('stored-token')
    expect(getToken()).toBe('stored-token')
    expect(window.localStorage.getItem('core-odoo.mission-control.token')).toBe('stored-token')

    const fetchMock = vi.fn().mockResolvedValue(jsonResponse([]))
    vi.stubGlobal('fetch', fetchMock)

    await api.projects.list()
    const [, init] = firstFetchCall(fetchMock)
    expect(new Headers(init.headers).get('Authorization')).toBe('Bearer stored-token')
  })

  it('clears the session and notifies subscribers on 401', async () => {
    setToken('expired-token')
    const handler = vi.fn()
    const unsubscribe = subscribeUnauthorized(handler)
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ detail: 'Token expired' }, 401))
    vi.stubGlobal('fetch', fetchMock)

    await expect(api.projects.list()).rejects.toMatchObject({
      status: 401,
      message: 'Token expired',
    })
    expect(getToken()).toBeNull()
    expect(handler).toHaveBeenCalledTimes(1)
    unsubscribe()
  })

  it('does not trigger the global logout for failed login attempts', async () => {
    const handler = vi.fn()
    const unsubscribe = subscribeUnauthorized(handler)
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ detail: 'Invalid credentials' }, 401))
    vi.stubGlobal('fetch', fetchMock)

    await expect(api.auth.login('admin', 'wrong')).rejects.toBeInstanceOf(ApiError)
    expect(handler).not.toHaveBeenCalled()
    unsubscribe()
  })

  it('parses error envelopes with codes and details', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(
        { error: { code: 'project_exists', message: 'Project already exists', details: { name: 'demo' } } },
        409,
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(api.projects.create({ name: 'demo', template: 'odoo' })).rejects.toMatchObject({
      status: 409,
      code: 'project_exists',
      message: 'Project already exists',
      details: { name: 'demo' },
    })
  })

  it('maps network failures to status 0', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    await expect(api.status()).rejects.toMatchObject({ status: 0, code: 'network' })
  })

  it('sends environment actions to the contract paths', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ stage: 'dev' }))
    vi.stubGlobal('fetch', fetchMock)

    await api.environments.restart('smoke test', 'dev')
    const [url, init] = firstFetchCall(fetchMock)
    expect(url).toBe('/api/v1/projects/smoke%20test/environments/dev/restart')
    expect(init.method).toBe('POST')
  })

  it('requests logs with the tail query parameter', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ logs: 'hello' }))
    vi.stubGlobal('fetch', fetchMock)

    await api.environments.logs('demo', 'prod', 500)
    const [url] = firstFetchCall(fetchMock)
    expect(url).toBe('/api/v1/projects/demo/environments/prod/logs?tail=500')
  })

  it('queries audit events with a limit', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse([]))
    vi.stubGlobal('fetch', fetchMock)

    await api.audit.list(100)
    const [url] = firstFetchCall(fetchMock)
    expect(url).toBe('/api/v1/audit?limit=100')
  })
})
