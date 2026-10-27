import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Check, Globe2, Info, KeyRound, LogOut, Moon, Server } from 'lucide-react'
import { API_BASE, api } from '../lib/api'
import { queryKeys } from '../lib/query'
import { parseStatus } from '../lib/status'
import { changeLanguage, type Language } from '../lib/i18n'
import { useAuth } from '../lib/auth-context'
import { useToast } from '../lib/toast-context'
import { PageHeader } from '../components/ui/PageHeader'
import { Card, CardContent, CardHeader } from '../components/ui/Card'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { cn } from '../lib/utils'
import { describeError } from '../lib/errors'
import { formatDateTime } from '../lib/format'
import { tokenExpiresAt } from '../lib/jwt'
import { Input, Label } from '../components/ui/Input'

const APP_VERSION = import.meta.env.VITE_APP_VERSION ?? '0.1.0'

export default function SettingsPage() {
  const { t, i18n } = useTranslation()
  const { user, token, logout } = useAuth()
  const { pushToast } = useToast()
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [repeatPassword, setRepeatPassword] = useState('')
  const sessionExpiry = tokenExpiresAt(token)
  const passwordMismatch = repeatPassword !== '' && repeatPassword !== newPassword
  const passwordTooShort = newPassword !== '' && newPassword.length < 8

  const changePasswordMutation = useMutation({
    mutationFn: () =>
      api.auth.changePassword({
        current_password: currentPassword,
        new_password: newPassword,
      }),
    onSuccess: () => {
      setCurrentPassword('')
      setNewPassword('')
      setRepeatPassword('')
      pushToast({ title: t('settings.passwordChanged'), variant: 'success' })
    },
    onError: (error) => {
      pushToast({
        title: t('settings.passwordChangeFailed'),
        description: describeError(error, t),
        variant: 'error',
      })
    },
  })
  const currentLanguage = ((i18n.resolvedLanguage ?? i18n.language ?? 'en').split('-')[0] ??
    'en') as string

  const statusQuery = useQuery({
    queryKey: queryKeys.status,
    queryFn: () => api.status(),
    staleTime: 30_000,
  })
  const healthQuery = useQuery({
    queryKey: queryKeys.health,
    queryFn: () => api.health(),
    staleTime: 30_000,
    retry: 1,
  })

  const status = statusQuery.data ? parseStatus(statusQuery.data, currentLanguage) : null
  const healthTone = healthQuery.isLoading
    ? 'neutral'
    : healthQuery.isError
      ? 'danger'
      : 'success'
  const healthLabel = healthQuery.isLoading
    ? t('settings.healthUnknown')
    : healthQuery.isError
      ? t('settings.healthError')
      : t('settings.healthOk')

  const languages: { value: Language; label: string }[] = [
    { value: 'en', label: t('settings.english') },
    { value: 'es', label: t('settings.spanish') },
  ]

  return (
    <>
      <PageHeader title={t('settings.title')} description={t('settings.subtitle')} />

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader title={t('settings.languageTitle')} description={t('settings.languageDescription')} />
          <CardContent>
            <div role="group" aria-label={t('settings.languageTitle')} className="grid gap-3 sm:grid-cols-2">
              {languages.map((language) => {
                const active = currentLanguage === language.value
                return (
                  <button
                    key={language.value}
                    type="button"
                    aria-pressed={active}
                    onClick={() => changeLanguage(language.value)}
                    className={cn(
                      'flex items-center justify-between gap-3 rounded-xl border px-4 py-3 text-left transition-colors',
                      'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-400',
                      active
                        ? 'border-accent-500/60 bg-accent-900/40'
                        : 'border-edge bg-surface-raised hover:border-edge-strong',
                    )}
                  >
                    <span className="flex items-center gap-2 text-sm font-medium text-slate-100">
                      <Globe2 className="h-4 w-4 text-slate-400" aria-hidden="true" />
                      {language.label}
                    </span>
                    {active ? (
                      <Check className="h-4 w-4 text-accent-300" aria-hidden="true" />
                    ) : null}
                  </button>
                )
              })}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader title={t('settings.sessionTitle')} description={t('settings.sessionDescription')} />
          <CardContent className="space-y-4">
            <div className="flex items-center gap-3 rounded-lg border border-edge bg-surface-muted px-4 py-3">
              <span className="flex h-9 w-9 items-center justify-center rounded-full bg-surface-raised text-slate-400">
                <KeyRound className="h-4 w-4" aria-hidden="true" />
              </span>
              <div className="min-w-0">
                <p className="text-xs text-slate-500">{t('common.username')}</p>
                <p className="truncate text-sm font-medium text-slate-100">
                  {user?.username ?? t('auth.userFallback')}
                </p>
                <p className="mt-0.5 text-[11px] uppercase tracking-wide text-slate-500">
                  {t('settings.role')}: {user?.role ?? 'viewer'}
                </p>
              </div>
            </div>
            {sessionExpiry ? (
              <p className="text-[11px] text-slate-500">
                {t('settings.sessionExpires', {
                  date: formatDateTime(sessionExpiry, currentLanguage),
                })}
              </p>
            ) : null}
            <div className="flex items-center justify-between gap-3">
              <p className="text-xs text-slate-500">{t('settings.logoutHint')}</p>
              <Button
                variant="danger"
                onClick={() => {
                  logout()
                  pushToast({ title: t('auth.signedOut'), variant: 'info' })
                }}
              >
                <LogOut className="h-4 w-4" aria-hidden="true" />
                {t('common.logout')}
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader
            title={t('settings.passwordTitle')}
            description={t('settings.passwordDescription')}
          />
          <CardContent>
            <form
              className="space-y-4"
              onSubmit={(event) => {
                event.preventDefault()
                changePasswordMutation.mutate()
              }}
            >
              <div>
                <Label htmlFor="current-password">{t('settings.currentPassword')}</Label>
                <Input
                  id="current-password"
                  type="password"
                  autoComplete="current-password"
                  value={currentPassword}
                  onChange={(event) => setCurrentPassword(event.target.value)}
                  required
                />
              </div>
              <div>
                <Label htmlFor="new-password">{t('settings.newPassword')}</Label>
                <Input
                  id="new-password"
                  type="password"
                  autoComplete="new-password"
                  value={newPassword}
                  onChange={(event) => setNewPassword(event.target.value)}
                  invalid={passwordTooShort}
                  required
                />
                {passwordTooShort ? (
                  <p className="mt-1 text-xs text-danger-400">{t('settings.passwordTooShort')}</p>
                ) : null}
              </div>
              <div>
                <Label htmlFor="repeat-password">{t('settings.repeatPassword')}</Label>
                <Input
                  id="repeat-password"
                  type="password"
                  autoComplete="new-password"
                  value={repeatPassword}
                  onChange={(event) => setRepeatPassword(event.target.value)}
                  invalid={passwordMismatch}
                  required
                />
                {passwordMismatch ? (
                  <p className="mt-1 text-xs text-danger-400">{t('settings.passwordMismatch')}</p>
                ) : null}
              </div>
              <div className="flex justify-end">
                <Button
                  type="submit"
                  variant="primary"
                  loading={changePasswordMutation.isPending}
                  disabled={
                    currentPassword === '' ||
                    newPassword.length < 8 ||
                    newPassword !== repeatPassword
                  }
                >
                  {changePasswordMutation.isPending
                    ? t('settings.changingPassword')
                    : t('settings.changePassword')}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>

        <Card>
          <CardHeader title={t('settings.apiTitle')} description={t('settings.apiDescription')} />
          <CardContent>
            <dl className="space-y-3 text-sm">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <dt className="text-xs text-slate-500">{t('settings.apiBase')}</dt>
                <dd className="max-w-full truncate rounded bg-surface-muted px-2 py-1 font-mono text-xs text-slate-300">
                  {API_BASE}
                </dd>
              </div>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <dt className="text-xs text-slate-500">{t('settings.health')}</dt>
                <dd>
                  <Badge tone={healthTone}>{healthLabel}</Badge>
                </dd>
              </div>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <dt className="text-xs text-slate-500">{t('settings.orchestratorVersion')}</dt>
                <dd className="flex items-center gap-2 text-xs text-slate-300">
                  <Server className="h-3.5 w-3.5 text-slate-500" aria-hidden="true" />
                  {status?.version ?? t('common.notAvailable')}
                </dd>
              </div>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <dt className="text-xs text-slate-500">{t('settings.uiVersion')}</dt>
                <dd className="font-mono text-xs text-slate-300">{APP_VERSION}</dd>
              </div>
            </dl>
            <p className="mt-4 border-t border-edge-muted pt-3 text-[11px] text-slate-500">
              {t('settings.apiBaseHint')}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader title={t('settings.appearanceTitle')} description={t('settings.appearanceDescription')} />
          <CardContent className="space-y-3">
            <div className="flex items-center justify-between gap-3 rounded-lg border border-accent-500/30 bg-accent-900/20 px-4 py-3">
              <span className="flex items-center gap-2 text-sm font-medium text-slate-100">
                <Moon className="h-4 w-4 text-accent-300" aria-hidden="true" />
                {t('settings.darkTheme')}
              </span>
              <Badge tone="info">{t('common.on')}</Badge>
            </div>
            <p className="text-xs text-slate-500">{t('settings.darkThemeHint')}</p>
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader title={t('settings.aboutTitle')} description={t('settings.aboutDescription')} />
          <CardContent className="flex items-start gap-3">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-surface-raised text-slate-400">
              <Info className="h-4 w-4" aria-hidden="true" />
            </span>
            <p className="text-sm text-slate-400">{t('app.description')}</p>
          </CardContent>
        </Card>
      </div>
    </>
  )
}
