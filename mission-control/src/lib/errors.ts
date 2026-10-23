import type { TFunction } from 'i18next'
import { ApiError } from './api'

/**
 * Maps API/network failures to localized, actionable messages. Server-provided
 * validation messages are preserved for 4xx responses.
 */
export function describeError(error: unknown, t: TFunction): string {
  if (error instanceof ApiError) {
    if (error.status === 0) return t('errors.network')
    if (error.status === 401) return t('errors.unauthorized')
    if (error.status === 403) return t('errors.forbidden')
    if (error.status === 404) return t('errors.notFound')
    if (error.status === 422 || error.status === 400) {
      return error.message || t('errors.validation')
    }
    if (error.status >= 500) return t('errors.server')
    return error.message || t('errors.requestFailed', { status: error.status })
  }
  if (error instanceof Error && error.message) return error.message
  if (typeof error === 'string' && error.trim() !== '') return error
  return t('errors.generic')
}

export function isUnauthorizedError(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401
}
