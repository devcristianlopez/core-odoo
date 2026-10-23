import { describe, expect, it } from 'vitest'
import { normalizeAuditEvent, normalizeAuditEvents } from './audit'

describe('normalizeAuditEvent', () => {
  it('maps common field aliases', () => {
    const event = normalizeAuditEvent({
      id: 'evt-1',
      ts: '2026-01-02T03:04:05Z',
      user: 'admin',
      event: 'deploy',
      project_name: 'demo',
      environment: 'dev',
      result: 'success',
      message: 'Deployed dev',
      details: { branch: 'main' },
    })
    expect(event).toEqual({
      id: 'evt-1',
      timestamp: '2026-01-02T03:04:05Z',
      actor: 'admin',
      action: 'deploy',
      project: 'demo',
      stage: 'dev',
      status: 'success',
      detail: 'Deployed dev',
    })
  })

  it('serializes object details and falls back to a generated id', () => {
    const event = normalizeAuditEvent({ action: 'login', details: { ip: '10.0.0.2' } }, 7)
    expect(event.id).toBe('event-7')
    expect(event.detail).toBe('{"ip":"10.0.0.2"}')
    expect(event.actor).toBeNull()
    expect(event.action).toBe('login')
  })

  it('tolerates malformed events', () => {
    expect(normalizeAuditEvent(null, 2).id).toBe('event-2')
    expect(normalizeAuditEvent(undefined).action).toBe('')
  })
})

describe('normalizeAuditEvents', () => {
  it('accepts arrays and wrapped collections', () => {
    expect(normalizeAuditEvents([{ action: 'a' }, { action: 'b' }])).toHaveLength(2)
    expect(normalizeAuditEvents({ items: [{ action: 'c' }] })).toHaveLength(1)
    expect(normalizeAuditEvents({ events: [{ action: 'd' }] })).toHaveLength(1)
  })

  it('returns an empty array for invalid payloads', () => {
    expect(normalizeAuditEvents(null)).toEqual([])
    expect(normalizeAuditEvents({ nope: true })).toEqual([])
    expect(normalizeAuditEvents('text')).toEqual([])
  })
})
