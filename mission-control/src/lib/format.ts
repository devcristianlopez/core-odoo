/**
 * Locale-aware formatting helpers. Units (B, KB, ms, …) are data, while all
 * natural-language output comes from `Intl` so it follows the active language.
 */

export function localeFor(language: string | undefined): string {
  if (!language) return 'en-US'
  const base = language.toLowerCase().split('-')[0]
  if (base === 'es') return 'es-ES'
  if (base === 'en') return 'en-US'
  return language
}

function toDate(value: string | number | Date | null | undefined): Date | null {
  if (value === null || value === undefined || value === '') return null
  const date = value instanceof Date ? value : new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}

export function formatDateTime(
  value: string | number | Date | null | undefined,
  language: string | undefined,
  fallback = '—',
): string {
  const date = toDate(value)
  if (!date) return fallback
  return new Intl.DateTimeFormat(localeFor(language), {
    dateStyle: 'medium',
    timeStyle: 'medium',
  }).format(date)
}

export function formatDate(
  value: string | number | Date | null | undefined,
  language: string | undefined,
  fallback = '—',
): string {
  const date = toDate(value)
  if (!date) return fallback
  return new Intl.DateTimeFormat(localeFor(language), { dateStyle: 'medium' }).format(date)
}

export function formatTime(
  value: string | number | Date | null | undefined,
  language: string | undefined,
  fallback = '—',
): string {
  const date = toDate(value)
  if (!date) return fallback
  return new Intl.DateTimeFormat(localeFor(language), {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(date)
}

/** Relative time using `Intl.RelativeTimeFormat` (localized, no hardcoded words). */
export function formatRelativeTime(
  value: string | number | Date | null | undefined,
  language: string | undefined,
  now: number = Date.now(),
  fallback = '—',
): string {
  const date = toDate(value)
  if (!date) return fallback
  const diffSeconds = Math.round((date.getTime() - now) / 1000)
  const abs = Math.abs(diffSeconds)
  const rtf = new Intl.RelativeTimeFormat(localeFor(language), { numeric: 'auto' })
  if (abs < 60) return rtf.format(Math.round(diffSeconds), 'second')
  if (abs < 3600) return rtf.format(Math.round(diffSeconds / 60), 'minute')
  if (abs < 86400) return rtf.format(Math.round(diffSeconds / 3600), 'hour')
  if (abs < 2592000) return rtf.format(Math.round(diffSeconds / 86400), 'day')
  if (abs < 31536000) return rtf.format(Math.round(diffSeconds / 2592000), 'month')
  return rtf.format(Math.round(diffSeconds / 31536000), 'year')
}

export function formatNumber(
  value: number | null | undefined,
  language: string | undefined,
  maximumFractionDigits = 0,
  fallback = '—',
): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return fallback
  return new Intl.NumberFormat(localeFor(language), { maximumFractionDigits }).format(value)
}

/** Formats a percentage where `value` is in the 0–100 range. */
export function formatPercent(
  value: number | null | undefined,
  language: string | undefined,
  maximumFractionDigits = 0,
  fallback = '—',
): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return fallback
  return new Intl.NumberFormat(localeFor(language), {
    style: 'percent',
    maximumFractionDigits,
  }).format(value / 100)
}

const BYTE_UNITS = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'] as const

export function formatBytes(
  value: number | null | undefined,
  language: string | undefined,
  maximumFractionDigits = 1,
  fallback = '—',
): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return fallback
  let amount = Math.max(0, value)
  let unitIndex = 0
  while (amount >= 1024 && unitIndex < BYTE_UNITS.length - 1) {
    amount /= 1024
    unitIndex += 1
  }
  const number = new Intl.NumberFormat(localeFor(language), {
    maximumFractionDigits: unitIndex === 0 ? 0 : maximumFractionDigits,
  }).format(amount)
  return `${number} ${BYTE_UNITS[unitIndex]}`
}

/** Formats a CPU core count (fractional cores) for charts and cards. */
export function formatCores(value: number | null | undefined, language: string | undefined): string {
  return formatNumber(value, language, 2)
}

/** Formats a duration in seconds using adaptive units. */
export function formatDurationSeconds(
  value: number | null | undefined,
  language: string | undefined,
): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  if (value < 1) return `${formatNumber(value * 1000, language, 0)} ms`
  if (value < 60) return `${formatNumber(value, language, 2)} s`
  return `${formatNumber(value / 60, language, 1)} min`
}

export function truncate(value: string, maxLength: number): string {
  if (value.length <= maxLength) return value
  return `${value.slice(0, Math.max(0, maxLength - 1))}…`
}
