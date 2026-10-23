import type { NormalizedAuditEvent } from './types'
import { isRecord } from './status'

function pickString(record: Record<string, unknown>, keys: string[]): string | null {
  for (const key of keys) {
    const value = record[key]
    if (typeof value === 'string' && value.trim() !== '') return value
    if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  }
  return null
}

function stringifyDetail(value: unknown): string | null {
  if (value === null || value === undefined) return null
  if (typeof value === 'string') return value.trim() === '' ? null : value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  try {
    return JSON.stringify(value)
  } catch {
    return null
  }
}

export function normalizeAuditEvent(event: unknown, index = 0): NormalizedAuditEvent {
  const record = isRecord(event) ? event : {}
  const timestamp = pickString(record, [
    'ts',
    'timestamp',
    'time',
    'created_at',
    'createdAt',
    'at',
    'date',
  ])
  const actor = pickString(record, ['actor', 'user', 'username', 'by', 'author'])
  const action = pickString(record, ['action', 'event', 'type', 'operation']) ?? ''
  const project = pickString(record, ['project', 'project_name', 'projectName'])
  const stage = pickString(record, ['stage', 'environment', 'env'])
  const status = pickString(record, ['status', 'result', 'outcome'])
  const detail =
    stringifyDetail(record.message) ??
    stringifyDetail(record.detail) ??
    stringifyDetail(record.details) ??
    stringifyDetail(record.error) ??
    stringifyDetail(record.description)
  const rawId = record.id ?? record.event_id ?? record.eventId
  const id =
    typeof rawId === 'string' || typeof rawId === 'number'
      ? String(rawId)
      : `${timestamp ?? 'event'}-${index}`

  return {
    id,
    timestamp,
    actor,
    action,
    project,
    stage,
    status,
    detail,
  }
}

export function normalizeAuditEvents(input: unknown): NormalizedAuditEvent[] {
  let list: unknown = input
  if (isRecord(input)) {
    list = input.items ?? input.events ?? input.audit ?? input.results
  }
  if (!Array.isArray(list)) return []
  return list.map((event, index) => normalizeAuditEvent(event, index))
}
