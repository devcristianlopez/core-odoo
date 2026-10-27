const BASE64_PADDING = 4

function decodeBase64Url(value: string): string {
  const normalized = value.replace(/-/g, '+').replace(/_/g, '/')
  const padded = normalized.padEnd(Math.ceil(normalized.length / BASE64_PADDING) * BASE64_PADDING, '=')
  return atob(padded)
}

/** Expiry of a JWT, or null when the token is missing or malformed. */
export function tokenExpiresAt(token: string | null): Date | null {
  if (!token) return null
  const payload = token.split('.')[1]
  if (!payload) return null
  try {
    const parsed = JSON.parse(decodeBase64Url(payload)) as { exp?: unknown }
    return typeof parsed.exp === 'number' ? new Date(parsed.exp * 1000) : null
  } catch {
    return null
  }
}
