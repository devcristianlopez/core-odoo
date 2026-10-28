import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import {
  Copy,
  Database,
  ExternalLink,
  Pause,
  Play,
  Rocket,
  RotateCw,
  Search,
  Square,
  Trash2,
  Undo2,
} from 'lucide-react'
import { api } from '../lib/api'
import { queryKeys, useRollbackEnvironment } from '../lib/query'
import { findEnvironment, safeHttpUrl } from '../lib/services'
import { buildEnvironmentQueries } from '../lib/metrics'
import { isRunningStatus } from '../lib/status'
import { formatDate, formatNumber, formatRelativeTime } from '../lib/format'
import { splitLogLines, filterLogLines, logsToText } from '../lib/logs'
import { copyText } from '../lib/clipboard'
import { describeError } from '../lib/errors'
import { useToast } from '../lib/toast-context'
import { useAuth } from '../lib/auth-context'
import { PageHeader } from '../components/ui/PageHeader'
import { Card, CardContent, CardHeader } from '../components/ui/Card'
import { Button } from '../components/ui/Button'
import { Input, Label, Select } from '../components/ui/Input'
import { ConfirmDialog } from '../components/ui/ConfirmDialog'
import { EmptyState } from '../components/ui/EmptyState'
import { ErrorState } from '../components/ui/ErrorState'
import { LoadingState, Skeleton } from '../components/ui/Loading'
import { StatusBadge } from '../components/StatusBadge'
import { ServiceBadges } from '../components/environments/ServiceBadges'
import { MetricChart } from '../components/metrics/MetricChart'
import { cn } from '../lib/utils'

const TAIL_OPTIONS = [100, 200, 500, 1000]

type EnvironmentAction = 'start' | 'stop' | 'restart'

export default function EnvironmentDetailPage() {
  const { t, i18n } = useTranslation()
  const language = i18n.resolvedLanguage ?? i18n.language
  const params = useParams<{ name: string; stage: string }>()
  const name = params.name ?? ''
  const stage = params.stage ?? ''
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { pushToast } = useToast()
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'
  const accessQuery = useQuery({
    queryKey: queryKeys.access(name),
    queryFn: () => api.projects.access(name),
    enabled: name !== '',
  })
  const projectRole = accessQuery.data?.role
  const canOperate =
    isAdmin || (user?.role === 'operator' && (projectRole === 'owner' || projectRole === 'developer'))
  const isProd = stage === 'prod'

  const [deleteOpen, setDeleteOpen] = useState(false)
  const [rollbackOpen, setRollbackOpen] = useState(false)
  const [promoteOpen, setPromoteOpen] = useState(false)
  const [metricsPaused, setMetricsPaused] = useState(false)
  const [logsPaused, setLogsPaused] = useState(false)
  const [autoScroll, setAutoScroll] = useState(true)
  const [tail, setTail] = useState(200)
  const [logFilter, setLogFilter] = useState('')
  const logsRef = useRef<HTMLPreElement>(null)

  const environmentsQuery = useQuery({
    queryKey: queryKeys.environments(name),
    queryFn: () => api.environments.list(name),
    enabled: name !== '' && stage !== '',
    refetchInterval: 10_000,
  })
  const environment = useMemo(
    () => findEnvironment(environmentsQuery.data ?? [], stage),
    [environmentsQuery.data, stage],
  )
  const queries = useMemo(() => buildEnvironmentQueries(name, stage), [name, stage])

  const logsQuery = useQuery({
    queryKey: queryKeys.logs(name, stage, tail),
    queryFn: () => api.environments.logs(name, stage, tail),
    enabled: Boolean(environment),
    refetchInterval: logsPaused ? false : 5_000,
    staleTime: 0,
  })

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.environments(name) })
    void queryClient.invalidateQueries({ queryKey: queryKeys.status })
    void queryClient.invalidateQueries({ queryKey: ['audit'] })
  }

  const stageLabel = (value: string) => t(`stages.${value}`, { defaultValue: value })

  const lifecycleMutation = useMutation({
    mutationFn: ({ action, environmentStage }: { action: EnvironmentAction; environmentStage: string }) => {
      if (action === 'start') return api.environments.start(name, environmentStage)
      if (action === 'stop') return api.environments.stop(name, environmentStage)
      return api.environments.restart(name, environmentStage)
    },
    onSuccess: (_result, variables) => {
      invalidate()
      const toastKey =
        variables.action === 'start'
          ? 'project.startToast'
          : variables.action === 'stop'
            ? 'project.stopToast'
            : 'project.restartToast'
      pushToast({
        title: t(toastKey, { project: name, stage: stageLabel(variables.environmentStage) }),
        variant: 'success',
      })
    },
    onError: (error) => {
      pushToast({
        title: t('environment.actionFailed'),
        description: describeError(error, t),
        variant: 'error',
      })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: () => api.environments.remove(name, stage, `${name}/${stage}`),
    onSuccess: () => {
      setDeleteOpen(false)
      invalidate()
      pushToast({
        title: t('project.environmentDeleted', { project: name, stage: stageLabel(stage) }),
        variant: 'success',
      })
      navigate(`/projects/${encodeURIComponent(name)}`)
    },
    onError: (error) => {
      pushToast({
        title: t('project.environmentDeleteFailed'),
        description: describeError(error, t),
        variant: 'error',
      })
    },
  })

  const rollbackMutation = useRollbackEnvironment(name)

  const promoteMutation = useMutation({
    mutationFn: () => api.environments.promote(name, stage, name),
    onSuccess: (promoted) => {
      setPromoteOpen(false)
      invalidate()
      pushToast({
        title: t('environment.promoted', {
          project: name,
          stage: stageLabel(promoted.stage),
        }),
        variant: 'success',
      })
    },
    onError: (error) => {
      pushToast({
        title: t('environment.promoteFailed'),
        description: describeError(error, t),
        variant: 'error',
      })
    },
  })

  const logLines = useMemo(() => splitLogLines(logsQuery.data?.logs), [logsQuery.data?.logs])
  const filteredLines = useMemo(() => filterLogLines(logLines, logFilter), [logLines, logFilter])

  useEffect(() => {
    if (!autoScroll || logsPaused) return
    const element = logsRef.current
    if (element) element.scrollTop = element.scrollHeight
  }, [filteredLines.length, autoScroll, logsPaused, logsQuery.dataUpdatedAt])

  if (environmentsQuery.isLoading) {
    return (
      <>
        <PageHeader
          title={name}
          back={{ to: `/projects/${encodeURIComponent(name)}`, label: t('environment.backToProject', { project: name }) }}
        />
        <LoadingState rows={5} />
      </>
    )
  }

  if (environmentsQuery.isError) {
    return (
      <>
        <PageHeader
          title={name}
          back={{ to: `/projects/${encodeURIComponent(name)}`, label: t('environment.backToProject', { project: name }) }}
        />
        <ErrorState
          error={environmentsQuery.error}
          title={t('environment.loadError')}
          onRetry={() => void environmentsQuery.refetch()}
        />
      </>
    )
  }

  if (!environment) {
    return (
      <>
        <PageHeader
          title={name}
          back={{ to: `/projects/${encodeURIComponent(name)}`, label: t('environment.backToProject', { project: name }) }}
        />
        <EmptyState
          title={t('environment.notFoundTitle')}
          description={t('environment.notFoundDescription')}
          action={
            <Link
              to={`/projects/${encodeURIComponent(name)}`}
              className="inline-flex h-9 items-center rounded-lg border border-edge bg-surface-raised px-3 text-xs font-medium text-slate-200 hover:bg-surface-overlay focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-400"
            >
              {t('environment.backToProject', { project: name })}
            </Link>
          }
        />
      </>
    )
  }

  const url = safeHttpUrl(environment.url)
  const running = isRunningStatus(environment.status)
  const pending = lifecycleMutation.isPending

  const copyUrl = async () => {
    if (!url) return
    try {
      await copyText(url)
      pushToast({ title: t('environment.copiedUrl'), variant: 'success' })
    } catch {
      pushToast({ title: t('common.copyFailed'), variant: 'error' })
    }
  }

  const copyLogs = async () => {
    try {
      await copyText(logsToText(filteredLines))
      pushToast({ title: t('environment.copiedLogs'), variant: 'success' })
    } catch {
      pushToast({ title: t('common.copyFailed'), variant: 'error' })
    }
  }

  const lastGoodIteration = environment.last_good_iteration ?? null
  const rollbackHint = lastGoodIteration
    ? t('environment.rollbackTo', { version: lastGoodIteration })
    : t('environment.rollbackUnavailable')

  const confirmRollback = () => {
    rollbackMutation.mutate(
      { stage, confirm: isProd ? name : undefined },
      {
        onSuccess: (rolledBack) => {
          setRollbackOpen(false)
          pushToast({
            title: t('environment.rollbackSuccess', {
              project: name,
              stage: stageLabel(stage),
              version: rolledBack.last_good_iteration ?? lastGoodIteration ?? '',
            }),
            variant: 'success',
          })
        },
        onError: (error) => {
          pushToast({
            title: t('environment.rollbackFailed'),
            description: describeError(error, t),
            variant: 'error',
          })
        },
      },
    )
  }

  return (
    <>
      <PageHeader
        back={{
          to: `/projects/${encodeURIComponent(name)}`,
          label: t('environment.backToProject', { project: name }),
        }}
        title={`${name} · ${stageLabel(stage)}`}
        description={t('environment.infoTitle')}
        actions={
          <>
            <StatusBadge status={environment.status} />
            {canOperate ? (
              <>
            <Button
              variant="ghost"
              size="icon"
              onClick={() =>
                lifecycleMutation.mutate({ action: 'start', environmentStage: environment.stage })
              }
              disabled={running || pending}
              aria-label={t('common.start')}
              title={t('common.start')}
            >
              <Play className="h-4 w-4" aria-hidden="true" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={() =>
                lifecycleMutation.mutate({ action: 'stop', environmentStage: environment.stage })
              }
              disabled={!running || pending}
              aria-label={t('common.stop')}
              title={t('common.stop')}
            >
              <Square className="h-4 w-4" aria-hidden="true" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={() =>
                lifecycleMutation.mutate({ action: 'restart', environmentStage: environment.stage })
              }
              disabled={pending}
              aria-label={t('common.restart')}
              title={t('common.restart')}
            >
              <RotateCw className="h-4 w-4" aria-hidden="true" />
            </Button>
            <span title={rollbackHint}>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setRollbackOpen(true)}
                disabled={!lastGoodIteration || pending || rollbackMutation.isPending}
                aria-label={rollbackHint}
                title={rollbackHint}
              >
                <Undo2 className="h-4 w-4" aria-hidden="true" />
                {t('environment.rollback')}
              </Button>
            </span>
            {lastGoodIteration ? null : (
              <span className="sr-only">{t('environment.rollbackUnavailable')}</span>
            )}
            {stage === 'staging' && isAdmin ? (
              <Button
                variant="primary"
                size="sm"
                onClick={() => setPromoteOpen(true)}
                disabled={pending || promoteMutation.isPending}
                aria-label={t('environment.promote')}
                title={t('environment.promote')}
              >
                <Rocket className="h-4 w-4" aria-hidden="true" />
                {t('environment.promote')}
              </Button>
            ) : null}
              </>
            ) : null}
            {environment.odoo_url ? (
              <a
                href={environment.odoo_url}
                target="_blank"
                rel="noreferrer noopener"
                className="inline-flex h-10 items-center gap-2 rounded-lg border border-edge bg-surface-raised px-3 text-sm font-medium text-slate-200 transition-colors hover:border-edge-strong hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-400"
                aria-label={t('environment.openOdoo')}
                title={t('environment.openOdoo')}
              >
                <Database className="h-4 w-4" aria-hidden="true" />
                Odoo
              </a>
            ) : null}
            {url ? (
              <a
                href={url}
                target="_blank"
                rel="noreferrer noopener"
                className="inline-flex h-10 items-center gap-2 rounded-lg border border-accent-500/40 bg-accent-600 px-4 text-sm font-medium text-white transition-colors hover:bg-accent-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-400 focus-visible:ring-offset-2 focus-visible:ring-offset-canvas"
              >
                <ExternalLink className="h-4 w-4" aria-hidden="true" />
                {t('environment.openUrl')}
              </a>
            ) : null}
            <Button
              variant="secondary"
              size="icon"
              onClick={() => {
                void environmentsQuery.refetch()
                void logsQuery.refetch()
              }}
              aria-label={t('common.refresh')}
              title={t('common.refresh')}
            >
              <RotateCw
                className={cn(
                  'h-4 w-4',
                  (environmentsQuery.isFetching || logsQuery.isFetching) && 'animate-spin',
                )}
                aria-hidden="true"
              />
            </Button>
            {isAdmin ? (
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setDeleteOpen(true)}
                aria-label={t('environment.deleteEnvironment')}
                title={t('environment.deleteEnvironment')}
                className="text-slate-500 hover:text-danger-400"
              >
                <Trash2 className="h-4 w-4" aria-hidden="true" />
              </Button>
            ) : null}
          </>
        }
      />

      <div className="grid gap-5 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader title={t('environment.infoTitle')} />
          <CardContent>
            <dl className="grid gap-4 sm:grid-cols-2">
              <div className="min-w-0 sm:col-span-2">
                <dt className="text-[11px] uppercase tracking-wide text-slate-500">
                  {t('environment.urlLabel')}
                </dt>
                <dd className="mt-1 flex flex-wrap items-center gap-2">
                  {url ? (
                    <>
                      <a
                        href={url}
                        target="_blank"
                        rel="noreferrer noopener"
                        className="min-w-0 truncate rounded text-sm text-accent-300 hover:text-accent-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-400"
                      >
                        {environment.url}
                      </a>
                      <Button variant="ghost" size="sm" onClick={() => void copyUrl()}>
                        <Copy className="h-3.5 w-3.5" aria-hidden="true" />
                        {t('environment.copyUrl')}
                      </Button>
                    </>
                  ) : (
                    <span className="text-sm text-slate-500">{t('environment.noUrl')}</span>
                  )}
                </dd>
              </div>
              <div className="min-w-0">
                <dt className="text-[11px] uppercase tracking-wide text-slate-500">
                  {t('environment.composeProject')}
                </dt>
                <dd className="mt-1 truncate font-mono text-xs text-slate-300">
                  {environment.compose_project || t('common.notAvailable')}
                </dd>
              </div>
              {environment.last_good_iteration ? (
                <div className="min-w-0">
                  <dt className="text-[11px] uppercase tracking-wide text-slate-500">
                    {t('environment.lastGoodIteration')}
                  </dt>
                  <dd className="mt-1 truncate font-mono text-xs text-slate-300">
                    {environment.last_good_iteration}
                  </dd>
                </div>
              ) : null}
              {environment.last_good_at ? (
                <div>
                  <dt className="text-[11px] uppercase tracking-wide text-slate-500">
                    {t('environment.lastGoodAt')}
                  </dt>
                  <dd
                    className="mt-1 text-sm text-slate-300"
                    title={formatDate(environment.last_good_at, language)}
                  >
                    {formatRelativeTime(environment.last_good_at, language)}
                  </dd>
                </div>
              ) : null}
              <div>
                <dt className="text-[11px] uppercase tracking-wide text-slate-500">
                  {t('common.updatedAt')}
                </dt>
                <dd className="mt-1 text-sm text-slate-300">
                  {formatRelativeTime(environment.updated_at, language)}
                </dd>
              </div>
              <div>
                <dt className="text-[11px] uppercase tracking-wide text-slate-500">
                  {t('common.createdAt')}
                </dt>
                <dd className="mt-1 text-sm text-slate-300">
                  {formatDate(environment.created_at, language)}
                </dd>
              </div>
              <div>
                <dt className="text-[11px] uppercase tracking-wide text-slate-500">
                  {t('common.stage')}
                </dt>
                <dd className="mt-1 text-sm text-slate-300">{stageLabel(environment.stage)}</dd>
              </div>
            </dl>
          </CardContent>
        </Card>

        <Card>
          <CardHeader title={t('environment.servicesTitle')} />
          <CardContent>
            <ServiceBadges
              services={environment.services}
              emptyLabel={t('environment.noServices')}
            />
          </CardContent>
        </Card>
      </div>

      <section aria-labelledby="metrics-heading" className="mt-6">
        <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 id="metrics-heading" className="text-sm font-semibold text-white">
              {t('environment.metricsTitle')}
            </h2>
            <p className="mt-0.5 text-xs text-slate-500">{t('environment.metricsHint')}</p>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[11px] text-slate-500">
              {t('common.autoRefresh')}: {metricsPaused ? t('common.off') : t('common.on')}
            </span>
            <Button
              variant="secondary"
              size="sm"
              aria-pressed={!metricsPaused}
              onClick={() => setMetricsPaused((current) => !current)}
            >
              {metricsPaused ? (
                <Play className="h-3.5 w-3.5" aria-hidden="true" />
              ) : (
                <Pause className="h-3.5 w-3.5" aria-hidden="true" />
              )}
              {metricsPaused ? t('common.resume') : t('common.pause')}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => void queryClient.invalidateQueries({ queryKey: ['metrics'] })}
            >
              <RotateCw className="h-3.5 w-3.5" aria-hidden="true" />
              {t('environment.refreshMetrics')}
            </Button>
          </div>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <MetricChart
            title={t('environment.cpuTitle')}
            description={t('environment.cpuUnit')}
            query={queries.cpu}
            format="cores"
            unitLabel={t('environment.cpuUnit')}
            color="accent"
            paused={metricsPaused}
          />
          <MetricChart
            title={t('environment.memoryTitle')}
            description={t('environment.memoryUnit')}
            query={queries.memory}
            format="bytes"
            unitLabel={t('environment.memoryUnit')}
            color="brand"
            paused={metricsPaused}
          />
          <MetricChart
            title={t('environment.p95Title')}
            description={t('environment.p95Unit')}
            query={queries.p95}
            format="seconds"
            unitLabel={t('environment.p95Unit')}
            color="warning"
            paused={metricsPaused}
          />
          <MetricChart
            title={t('environment.errorRateTitle')}
            description={t('environment.errorRateUnit')}
            query={queries.errorRate}
            format="rate"
            unitLabel={t('environment.errorRateUnit')}
            color="danger"
            paused={metricsPaused}
          />
        </div>
      </section>

      <Card className="mt-6">
        <CardHeader
          title={t('environment.logsTitle')}
          description={t('environment.logsHint')}
          actions={
            <div className="flex flex-wrap items-center gap-2">
              <label htmlFor="logs-tail" className="sr-only">
                {t('environment.tailLabel')}
              </label>
              <Select
                id="logs-tail"
                value={tail}
                onChange={(event) => setTail(Number(event.target.value))}
                className="h-8 w-24 text-xs"
              >
                {TAIL_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {formatNumber(option, language)}
                  </option>
                ))}
              </Select>
              <Button
                variant="secondary"
                size="sm"
                aria-pressed={logsPaused}
                onClick={() => setLogsPaused((current) => !current)}
              >
                {logsPaused ? (
                  <Play className="h-3.5 w-3.5" aria-hidden="true" />
                ) : (
                  <Pause className="h-3.5 w-3.5" aria-hidden="true" />
                )}
                {logsPaused ? t('common.resume') : t('common.pause')}
              </Button>
              <Button variant="ghost" size="sm" onClick={() => void logsQuery.refetch()}>
                <RotateCw className="h-3.5 w-3.5" aria-hidden="true" />
                {t('environment.refreshLogs')}
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setAutoScroll((current) => !current)}
                aria-pressed={autoScroll}
              >
                {t('environment.autoScroll')}: {autoScroll ? t('common.on') : t('common.off')}
              </Button>
            </div>
          }
        />
        <div className="flex flex-col gap-3 border-b border-edge-muted px-5 py-3 sm:flex-row sm:items-end">
          <div className="w-full sm:max-w-xs">
            <Label htmlFor="logs-filter">{t('environment.filterLabel')}</Label>
            <div className="relative">
              <Search
                className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-500"
                aria-hidden="true"
              />
              <Input
                id="logs-filter"
                type="search"
                value={logFilter}
                onChange={(event) => setLogFilter(event.target.value)}
                placeholder={t('environment.filterPlaceholder')}
                className="h-9 pl-8 text-xs"
              />
            </div>
          </div>
          <div className="flex items-center gap-2 sm:ml-auto">
            <span className="text-[11px] text-slate-500">
              {t('common.showingCount', {
                shown: formatNumber(filteredLines.length, language),
                total: formatNumber(logLines.length, language),
              })}{' '}
              {t('common.lines')}
            </span>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => void copyLogs()}
              disabled={filteredLines.length === 0}
            >
              <Copy className="h-3.5 w-3.5" aria-hidden="true" />
              {t('environment.copyLogs')}
            </Button>
          </div>
        </div>
        <CardContent className="p-0">
          {logsQuery.isLoading ? (
            <div className="space-y-2 p-5" role="status">
              <span className="sr-only">{t('common.loading')}</span>
              {Array.from({ length: 8 }).map((_, index) => (
                <Skeleton key={index} className={index % 3 === 0 ? 'h-3 w-3/4' : 'h-3 w-1/2'} />
              ))}
            </div>
          ) : logsQuery.isError ? (
            <div className="p-4">
              <ErrorState
                error={logsQuery.error}
                title={t('environment.logsError')}
                onRetry={() => void logsQuery.refetch()}
              />
            </div>
          ) : filteredLines.length === 0 ? (
            <div className="p-5">
              <EmptyState
                title={logLines.length === 0 ? t('environment.noLogsTitle') : t('common.noResults')}
                description={logLines.length === 0 ? t('environment.noLogsHint') : undefined}
                action={
                  logLines.length > 0 ? (
                    <Button variant="ghost" size="sm" onClick={() => setLogFilter('')}>
                      {t('common.clear')}
                    </Button>
                  ) : undefined
                }
              />
            </div>
          ) : (
            <pre
              ref={logsRef}
              tabIndex={0}
              aria-label={t('environment.logsTitle')}
              className="max-h-[34rem] overflow-auto whitespace-pre-wrap break-words bg-black/40 p-4 font-mono text-[11px] leading-relaxed text-slate-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent-500"
            >
              {filteredLines.join('\n')}
            </pre>
          )}
        </CardContent>
      </Card>

      <ConfirmDialog
        open={deleteOpen}
        onClose={() => {
          if (!deleteMutation.isPending) setDeleteOpen(false)
        }}
        onConfirm={() => deleteMutation.mutate()}
        title={t('environment.deleteTitle')}
        description={t('environment.deleteDescription', { project: name, stage: stageLabel(stage) })}
        warning={t('environment.deleteWarning')}
        confirmLabel={
          deleteMutation.isPending ? t('common.deleting') : t('environment.deleteEnvironment')
        }
        requireText={`${name}/${stage}`}
        requireTextHint={t('common.confirmValue', { value: `${name}/${stage}` })}
        destructive
        loading={deleteMutation.isPending}
      />

      <ConfirmDialog
        open={rollbackOpen}
        onClose={() => {
          if (!rollbackMutation.isPending) setRollbackOpen(false)
        }}
        onConfirm={confirmRollback}
        title={t('environment.rollbackTitle')}
        description={t('environment.rollbackDescription', {
          project: name,
          stage: stageLabel(stage),
          version: lastGoodIteration ?? '',
        })}
        warning={isProd ? t('environment.rollbackProdWarning') : undefined}
        confirmLabel={
          rollbackMutation.isPending ? t('environment.rollingBack') : t('environment.rollback')
        }
        requireText={isProd ? name : undefined}
        requireTextHint={isProd ? t('common.confirmValue', { value: name }) : undefined}
        destructive={isProd}
        loading={rollbackMutation.isPending}
      />

      <ConfirmDialog
        open={promoteOpen}
        onClose={() => {
          if (!promoteMutation.isPending) setPromoteOpen(false)
        }}
        onConfirm={() => promoteMutation.mutate()}
        title={t('environment.promoteTitle')}
        description={t('environment.promoteDescription', {
          project: name,
          stage: stageLabel(stage),
        })}
        warning={t('environment.promoteWarning')}
        confirmLabel={
          promoteMutation.isPending ? t('environment.promoting') : t('environment.promote')
        }
        requireText={name}
        requireTextHint={t('common.confirmValue', { value: name })}
        destructive
        loading={promoteMutation.isPending}
      />
    </>
  )
}
