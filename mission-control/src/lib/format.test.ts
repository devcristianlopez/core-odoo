import { describe, expect, it } from 'vitest'
import {
  formatBytes,
  formatDate,
  formatDateTime,
  formatDurationSeconds,
  formatNumber,
  formatPercent,
  formatRelativeTime,
  localeFor,
  truncate,
} from './format'

describe('localeFor', () => {
  it('normalizes supported languages and keeps unknown locales', () => {
    expect(localeFor('es')).toBe('es-ES')
    expect(localeFor('es-MX')).toBe('es-ES')
    expect(localeFor('en')).toBe('en-US')
    expect(localeFor('en-GB')).toBe('en-US')
    expect(localeFor('fr-FR')).toBe('fr-FR')
    expect(localeFor(undefined)).toBe('en-US')
  })
})

describe('number and percentage formatting', () => {
  it('formats numbers with locale separators', () => {
    expect(formatNumber(1234.56, 'en', 2)).toBe('1,234.56')
    expect(formatNumber(null, 'en')).toBe('—')
  })

  it('formats 0–100 percentages', () => {
    expect(formatPercent(42, 'en')).toBe('42%')
    expect(formatPercent(12.345, 'en', 1)).toBe('12.3%')
    expect(formatPercent(Number.NaN, 'en')).toBe('—')
  })

  it('formats bytes with adaptive units', () => {
    expect(formatBytes(512, 'en')).toBe('512 B')
    expect(formatBytes(1536, 'en')).toBe('1.5 KB')
    expect(formatBytes(5 * 1024 ** 3, 'en')).toBe('5 GB')
    expect(formatBytes(null, 'en')).toBe('—')
  })

  it('formats durations', () => {
    expect(formatDurationSeconds(0.25, 'en')).toBe('250 ms')
    expect(formatDurationSeconds(2.5, 'en')).toBe('2.5 s')
    expect(formatDurationSeconds(90, 'en')).toBe('1.5 min')
  })
})

describe('date formatting', () => {
  it('returns the fallback for invalid values', () => {
    expect(formatDate('not-a-date', 'en')).toBe('—')
    expect(formatDateTime(null, 'es')).toBe('—')
  })

  it('formats ISO timestamps', () => {
    expect(formatDate('2026-01-02T12:00:00Z', 'en')).toContain('2026')
  })

  it('formats relative times using Intl', () => {
    const now = Date.parse('2026-01-02T12:00:00Z')
    expect(formatRelativeTime(now - 60_000, 'en', now)).toBe('1 minute ago')
    expect(formatRelativeTime(now - 3_600_000, 'es', now)).toContain('hora')
    expect(formatRelativeTime(null, 'en', now)).toBe('—')
  })
})

describe('truncate', () => {
  it('adds an ellipsis only when needed', () => {
    expect(truncate('abcdef', 4)).toBe('abc…')
    expect(truncate('abc', 4)).toBe('abc')
  })
})
