import { describe, expect, it } from 'vitest'
import {
  asNumber,
  hostMetric,
  isRunningStatus,
  normalizeStatusKey,
  parseBytes,
  parseStatus,
  statusTone,
} from './status'

describe('status normalization', () => {
  it('normalizes status keys', () => {
    expect(normalizeStatusKey(' Running ')).toBe('running')
    expect(normalizeStatusKey('Not Ready')).toBe('not-ready')
    expect(normalizeStatusKey(undefined)).toBe('unknown')
  })

  it('maps statuses to tones', () => {
    expect(statusTone('running')).toBe('success')
    expect(statusTone('deploying')).toBe('warning')
    expect(statusTone('failed')).toBe('danger')
    expect(statusTone('stopped')).toBe('neutral')
    expect(statusTone(undefined)).toBe('neutral')
  })

  it('detects running states', () => {
    expect(isRunningStatus('RUNNING')).toBe(true)
    expect(isRunningStatus('healthy')).toBe(true)
    expect(isRunningStatus('stopped')).toBe(false)
  })
})

describe('parseBytes and asNumber', () => {
  it('parses byte strings with binary units', () => {
    expect(parseBytes(1024)).toBe(1024)
    expect(parseBytes('1.5 GiB')).toBe(1.5 * 1024 ** 3)
    expect(parseBytes('512 MB')).toBe(512 * 1024 ** 2)
    expect(parseBytes('nope')).toBeNull()
  })

  it('parses numeric strings including percentages', () => {
    expect(asNumber('42%')).toBe(42)
    expect(asNumber('3.5')).toBe(3.5)
    expect(asNumber('')).toBeNull()
    expect(asNumber(Number.NaN)).toBeNull()
  })
})

describe('hostMetric', () => {
  it('accepts percentages', () => {
    expect(hostMetric(42)).toEqual({ percent: 42, detail: null })
    expect(hostMetric('12.5%')).toEqual({ percent: 12.5, detail: null })
  })

  it('computes percent and detail from used/total', () => {
    expect(hostMetric({ used: 4 * 1024 ** 3, total: 8 * 1024 ** 3 }, 'en')).toEqual({
      percent: 50,
      detail: '4 GB / 8 GB',
    })
  })

  it('computes used and percent from free/total', () => {
    // The card always reports used / total, so a free/total payload is
    // converted before it is displayed.
    expect(hostMetric({ free: 1024 ** 3, total: 4 * 1024 ** 3 }, 'en')).toEqual({
      percent: 75,
      detail: '3 GB / 4 GB',
    })
  })

  it('reads explicit percentage keys and byte strings', () => {
    const metric = hostMetric(
      { used_percent: 71, used: '20 GB', total: '40 GB' },
      'en',
    )
    expect(metric.percent).toBe(71)
    expect(metric.detail).toBe('20 GB / 40 GB')
  })

  it('returns empty metrics for unsupported values', () => {
    expect(hostMetric(undefined)).toEqual({ percent: null, detail: null })
    expect(hostMetric({})).toEqual({ percent: null, detail: null })
  })
})

describe('parseStatus', () => {
  it('parses a rich status payload', () => {
    const status = parseStatus(
      {
        docker: { available: true, version: '27.1.1' },
        disk: { percent: 71, used: '20 GB', total: '40 GB' },
        environments: { total: 3, running: 1 },
        version: '0.2.0',
        cpu: { used_percent: 12.5 },
        memory: { used: 4 * 1024 ** 3, total: 8 * 1024 ** 3 },
      },
      'en',
    )
    expect(status.version).toBe('0.2.0')
    expect(status.docker).toEqual({ online: true, label: '27.1.1' })
    expect(status.environments).toEqual({ total: 3, running: 1 })
    expect(status.cpu.percent).toBe(12.5)
    expect(status.memory.percent).toBe(50)
    expect(status.disk.percent).toBe(71)
    expect(status.disk.detail).toBe('20 GB / 40 GB')
  })

  it('tolerates alternate shapes', () => {
    const status = parseStatus({
      docker: 'down',
      disk: 42,
      environments: [{ status: 'running' }, { status: 'stopped' }],
      cpu: 0.5,
    })
    expect(status.docker.online).toBe(false)
    expect(status.disk.percent).toBe(42)
    expect(status.environments).toEqual({ total: 2, running: 1 })
    expect(status.cpu.percent).toBe(0.5)
  })

  it('does not throw on empty payloads', () => {
    const status = parseStatus(null)
    expect(status.docker).toEqual({ online: null, label: null })
    expect(status.environments).toEqual({ total: null, running: null })
    expect(status.cpu.percent).toBeNull()
  })
})
