import { describe, expect, it } from 'vitest'
import { tokenExpiresAt } from './jwt'

function tokenWith(payload: Record<string, unknown>): string {
  const encode = (value: object) =>
    btoa(JSON.stringify(value)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
  return `${encode({ alg: 'HS256', typ: 'JWT' })}.${encode(payload)}.signature`
}

describe('tokenExpiresAt', () => {
  it('reads the exp claim', () => {
    const expires = Math.floor(Date.now() / 1000) + 60
    expect(tokenExpiresAt(tokenWith({ exp: expires }))?.getTime()).toBe(expires * 1000)
  })

  it('returns null without a token', () => {
    expect(tokenExpiresAt(null)).toBeNull()
  })

  it('returns null for malformed tokens', () => {
    expect(tokenExpiresAt('not-a-jwt')).toBeNull()
    expect(tokenExpiresAt('a.b.c')).toBeNull()
  })
})
