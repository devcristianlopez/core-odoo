import { useState, type FormEvent } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { Boxes, Eye, EyeOff, LockKeyhole, UserRound } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../lib/auth-context'
import { ApiError } from '../lib/api'
import { describeError } from '../lib/errors'
import { Button } from '../components/ui/Button'
import { Input } from '../components/ui/Input'
import { LanguageSwitcher } from '../components/LanguageSwitcher'

interface LoginLocationState {
  from?: unknown
}

function safeRedirect(from: unknown): string {
  if (typeof from !== 'string') return '/'
  if (!from.startsWith('/') || from.startsWith('//')) return '/'
  return from
}

export default function LoginPage() {
  const { t } = useTranslation()
  const { login, isAuthenticated, isInitializing } = useAuth()
  const location = useLocation()
  const redirectTo = safeRedirect((location.state as LoginLocationState | null)?.from)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<{ username?: string; password?: string }>({})

  if (isAuthenticated && !isInitializing) {
    return <Navigate to={redirectTo} replace />
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const nextErrors: { username?: string; password?: string } = {}
    if (username.trim() === '') nextErrors.username = t('auth.missingUsername')
    if (password === '') nextErrors.password = t('auth.missingPassword')
    setFieldErrors(nextErrors)
    setFormError(null)
    if (Object.keys(nextErrors).length > 0) return

    setSubmitting(true)
    try {
      await login(username.trim(), password)
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setFormError(t('auth.invalidCredentials'))
      } else {
        setFormError(describeError(error, t))
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-canvas px-4 py-10">
      <div
        className="pointer-events-none absolute inset-0 opacity-70"
        aria-hidden="true"
        style={{
          background:
            'radial-gradient(60rem 40rem at 15% 0%, rgba(113,75,103,0.28), transparent 60%), radial-gradient(50rem 35rem at 90% 100%, rgba(1,126,132,0.22), transparent 60%)',
        }}
      />
      <div className="absolute right-4 top-4 z-10">
        <LanguageSwitcher />
      </div>

      <main className="relative z-10 w-full max-w-md">
        <div className="mb-8 flex flex-col items-center text-center">
          <span className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-brand-500 via-brand-600 to-accent-700 shadow-glow">
            <Boxes className="h-7 w-7 text-white" aria-hidden="true" />
          </span>
          <h1 className="text-2xl font-semibold tracking-tight text-white">{t('auth.title')}</h1>
          <p className="mt-2 text-sm text-slate-400">{t('auth.subtitle')}</p>
        </div>

        <div className="rounded-2xl border border-edge bg-surface/95 p-6 shadow-2xl backdrop-blur sm:p-8">
          <form onSubmit={handleSubmit} noValidate className="space-y-5">
            {formError ? (
              <p
                id="login-error"
                role="alert"
                className="rounded-lg border border-danger-500/40 bg-danger-900/30 px-3 py-2 text-sm text-danger-400"
              >
                {formError}
              </p>
            ) : null}

            <div>
              <label htmlFor="login-username" className="mb-1.5 block text-xs font-medium text-slate-300">
                {t('auth.usernameLabel')}
              </label>
              <div className="relative">
                <UserRound
                  className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500"
                  aria-hidden="true"
                />
                <Input
                  id="login-username"
                  name="username"
                  autoComplete="username"
                  autoFocus
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                  placeholder={t('auth.usernamePlaceholder')}
                  className="pl-9"
                  invalid={Boolean(fieldErrors.username)}
                  aria-describedby={fieldErrors.username ? 'login-username-error' : undefined}
                  disabled={submitting}
                />
              </div>
              {fieldErrors.username ? (
                <p id="login-username-error" role="alert" className="mt-1.5 text-xs text-danger-400">
                  {fieldErrors.username}
                </p>
              ) : null}
            </div>

            <div>
              <label htmlFor="login-password" className="mb-1.5 block text-xs font-medium text-slate-300">
                {t('auth.passwordLabel')}
              </label>
              <div className="relative">
                <LockKeyhole
                  className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500"
                  aria-hidden="true"
                />
                <Input
                  id="login-password"
                  name="password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="current-password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder={t('auth.passwordPlaceholder')}
                  className="pl-9 pr-11"
                  invalid={Boolean(fieldErrors.password)}
                  aria-describedby={fieldErrors.password ? 'login-password-error' : undefined}
                  disabled={submitting}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((current) => !current)}
                  aria-label={showPassword ? t('auth.hidePassword') : t('auth.showPassword')}
                  className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded-md p-1.5 text-slate-500 transition-colors hover:bg-surface-raised hover:text-slate-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-400"
                >
                  {showPassword ? (
                    <EyeOff className="h-4 w-4" aria-hidden="true" />
                  ) : (
                    <Eye className="h-4 w-4" aria-hidden="true" />
                  )}
                </button>
              </div>
              {fieldErrors.password ? (
                <p id="login-password-error" role="alert" className="mt-1.5 text-xs text-danger-400">
                  {fieldErrors.password}
                </p>
              ) : null}
            </div>

            <Button type="submit" variant="primary" size="lg" className="w-full" loading={submitting}>
              {submitting ? t('auth.submitting') : t('auth.submit')}
            </Button>
          </form>

          <p className="mt-6 border-t border-edge-muted pt-4 text-center text-xs text-slate-500">
            {t('auth.footer')}
          </p>
        </div>

        <p className="mt-6 text-center text-xs text-slate-600">{t('app.tagline')}</p>
      </main>
    </div>
  )
}
