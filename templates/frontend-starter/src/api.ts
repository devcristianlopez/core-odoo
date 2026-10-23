/**
 * Copyright 2026 Core Odoo contributors
 * SPDX-License-Identifier: Apache-2.0
 *
 * The only network dependency of the app. In production nginx proxies `/api`
 * to the gateway; in development Vite proxies it to http://localhost:8000.
 * Declared resources and fields come from the project's `backend.yaml`.
 */

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, '') ?? ''

export interface ResourceRecord {
  id: number
  [field: string]: unknown
}

export class ApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function findRows(payload: unknown): Record<string, unknown>[] {
  if (Array.isArray(payload)) {
    return payload.filter(isRecord)
  }
  if (isRecord(payload)) {
    for (const key of ['items', 'data', 'records', 'results']) {
      if (key in payload) {
        const rows = findRows(payload[key])
        if (rows.length > 0) return rows
      }
    }
  }
  return []
}

function toRecord(payload: unknown, fallbackId?: number): ResourceRecord {
  if (Array.isArray(payload)) {
    return toRecord(payload[0], fallbackId)
  }
  if (isRecord(payload)) {
    if (payload.id !== undefined) {
      return { ...payload, id: Number(payload.id) }
    }
    for (const key of ['data', 'result', 'record']) {
      if (key in payload) {
        return toRecord(payload[key], fallbackId)
      }
    }
  }
  if (fallbackId !== undefined) {
    return { id: fallbackId }
  }
  throw new ApiError('Gateway response did not include a record', 0)
}

async function request(path: string, init: RequestInit = {}): Promise<unknown> {
  const headers = new Headers(init.headers)
  headers.set('Accept', 'application/json')
  if (init.body !== undefined) headers.set('Content-Type', 'application/json')

  const response = await fetch(`${API_BASE}${path}`, { ...init, headers })
  if (!response.ok) {
    const detail = await response.text().catch(() => '')
    throw new ApiError(detail.slice(0, 300) || `HTTP ${response.status}`, response.status)
  }
  if (response.status === 204) return undefined
  return (await response.json()) as unknown
}

export class ResourceClient {
  constructor(private readonly resource: string) {}

  async list(params: Record<string, string | number> = {}): Promise<ResourceRecord[]> {
    const query = new URLSearchParams()
    for (const [key, value] of Object.entries(params)) {
      query.set(key, String(value))
    }
    const suffix = query.toString() ? `?${query.toString()}` : ''
    return findRows(await request(`/api/${this.resource}${suffix}`)).map((row) => toRecord(row))
  }

  async read(id: number): Promise<ResourceRecord> {
    return toRecord(await request(`/api/${this.resource}/${id}`), id)
  }

  async create(values: Record<string, unknown>): Promise<ResourceRecord> {
    return toRecord(await request(`/api/${this.resource}`, {
      method: 'POST',
      body: JSON.stringify(values),
    }))
  }

  async update(id: number, values: Record<string, unknown>): Promise<ResourceRecord> {
    return toRecord(await request(`/api/${this.resource}/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(values),
    }), id)
  }

  async remove(id: number): Promise<void> {
    await request(`/api/${this.resource}/${id}`, { method: 'DELETE' })
  }
}

export const RESOURCE = (import.meta.env.VITE_RESOURCE as string | undefined) ?? 'contacts'
export const client = new ResourceClient(RESOURCE)
