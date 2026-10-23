/**
 * Copyright 2026 Core Odoo contributors
 * SPDX-License-Identifier: Apache-2.0
 *
 * Browser → nginx `/api/` → gateway → Odoo. Odoo is never called directly.
 */
const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, '') ?? ''

export interface Contact {
  id: number
  name: string
  nickname?: string | null
  email?: string | null
  phone?: string | null
  city?: string | null
}

export interface ContactInput {
  name: string
  nickname?: string | null
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

function extractId(payload: unknown): number {
  if (isRecord(payload)) {
    const candidates: unknown[] = [payload.id]
    for (const key of ['data', 'result', 'record']) {
      const nested = payload[key]
      if (isRecord(nested)) candidates.push(nested.id)
    }
    for (const candidate of candidates) {
      const value = typeof candidate === 'string' ? Number(candidate) : candidate
      if (typeof value === 'number' && Number.isFinite(value)) return value
    }
  }
  throw new ApiError('Gateway response did not include a record id', 0)
}

function toContact(record: Record<string, unknown>): Contact {
  return {
    id: Number(record.id),
    name: typeof record.name === 'string' ? record.name : '',
    nickname: typeof record.nickname === 'string' ? record.nickname : null,
    email: typeof record.email === 'string' ? record.email : null,
    phone: typeof record.phone === 'string' ? record.phone : null,
    city: typeof record.city === 'string' ? record.city : null,
  }
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

export async function listContacts(): Promise<Contact[]> {
  const payload = await request('/api/contacts?limit=100&order=name%20asc')
  return findRows(payload).map(toContact)
}

export async function createContact(input: ContactInput): Promise<Contact> {
  const payload = await request('/api/contacts', {
    method: 'POST',
    body: JSON.stringify(input),
  })
  return {
    id: extractId(payload),
    name: input.name,
    nickname: input.nickname ?? null,
  }
}
