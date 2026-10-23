import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  api,
  clearToken,
  getToken,
  setToken,
  subscribeUnauthorized,
} from './api'
import { isUnauthorizedError } from './errors'
import { AuthContext, type AuthContextValue } from './auth-context'
import type { MeResponse } from './types'

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [token, setTokenState] = useState<string | null>(() => getToken())
  const [user, setUser] = useState<MeResponse | null>(null)
  const [isInitializing, setIsInitializing] = useState<boolean>(() => getToken() !== null)

  const clearSession = useCallback(() => {
    clearToken()
    setTokenState(null)
    setUser(null)
    setIsInitializing(false)
    queryClient.clear()
  }, [queryClient])

  // A 401 from any request ends the session, including expired JWTs.
  useEffect(() => subscribeUnauthorized(clearSession), [clearSession])

  // Bootstrap the session once on mount. Login() performs its own /auth/me call.
  useEffect(() => {
    let active = true
    const stored = getToken()
    if (!stored) {
      setIsInitializing(false)
      return () => {
        active = false
      }
    }
    setIsInitializing(true)
    api.auth
      .me()
      .then((me) => {
        if (active) setUser(me)
      })
      .catch((error: unknown) => {
        if (!active) return
        if (isUnauthorizedError(error)) {
          clearSession()
        } else {
          // Keep the token: the control plane may be temporarily unreachable.
          setUser(null)
        }
      })
      .finally(() => {
        if (active) setIsInitializing(false)
      })
    return () => {
      active = false
    }
  }, [clearSession])

  const login = useCallback(
    async (username: string, password: string) => {
      const response = await api.auth.login(username, password)
      setToken(response.access_token)
      setTokenState(response.access_token)
      setUser(null)
      try {
        const me = await api.auth.me()
        setUser(me)
      } catch (error) {
        if (isUnauthorizedError(error)) {
          clearSession()
          throw error
        }
        // Login succeeded; a transient /auth/me failure should not log out.
      }
    },
    [clearSession],
  )

  const logout = useCallback(() => {
    clearSession()
  }, [clearSession])

  const value = useMemo<AuthContextValue>(
    () => ({
      token,
      user,
      isAuthenticated: token !== null,
      isInitializing,
      login,
      logout,
    }),
    [token, user, isInitializing, login, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
