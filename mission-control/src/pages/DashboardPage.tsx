import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import {
  Activity,
  ChevronRight,
  Cpu,
  FolderKanban,
  HardDrive,
  MemoryStick,
  RotateCw,
  ScrollText,
  Server,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { api } from '../lib/api'
import { queryKeys } from '../lib/query'
import { parseStatus, isRunningStatus } from '../lib/status'
import { flattenEnvironments } from '../lib/services'
import { normalizeAuditEvents } from '../lib/audit'
import { HOST_QUERIES, latestMetricValue } from '../lib/metrics'
import {
  formatNumber,
  formatPercent,
  formatRelativeTime,
} from '../lib/format'
import { PageHeader } from '../components/ui/PageHeader'
import { Card, CardContent, CardHeader } from '../components/ui/Card'
import { Button } from '../components/ui/Button'
import { Badge } from '../components/ui/Badge'
import { EmptyState } from '../components/ui/EmptyState'
import { ErrorState } from '../components/ui/ErrorState'
import { LoadingState, Skeleton } from '../components/ui/Loading'
import { StatusBadge } from '../components/StatusBadge'
import type { HostMetric } from '../lib/types'
import { cn } from '../lib/utils'

interface StatCardProps {
  label: string
  value: string
  hint: string
  icon: LucideIcon
  loading?: boolean
  percent?: number | null
}

function usageBarClass(percent: number): string {
  if (percent >= 85) return 'bg-danger-500'
  if (percent >= 70) return 'bg-warning-500'
  return 'bg-accent-500'
}

function StatCard({ label, value, hint, icon: Icon, loading = false, percent }: StatCardProps) {
  return (
    <Card className="p-5">
      <div className="flex items-start justify-between gap-3">
        <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-surface-raised text-slate-400">
          <Icon className="h-4 w-4" aria-hidden="true" />
        </span>
      </div>
      {loading ? (
        <Skeleton className="mt-3 h-8 w-20" />
      ) : (
        <p className="mt-2 text-2xl font-semibold tabular-nums tracking-tight text-white">{value}</p>
      )}
      <p className="mt-1 truncate text-xs text-slate-500" title={hint}>
        {hint}
      </p>
      {typeof percent === 'number' ? (
        <div
          role="progressbar"
          aria-label={label}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(percent)}
          className="mt-3 h-1.5 overflow-hidden rounded-full bg-surface-overlay"
        >
          <div
            className={cn('h-full rounded-full transition-all', usageBarClass(percent))}
            style={{ width: `${Math.min(100, Math.max(0, percent))}%` }}
          />
        </div>
      ) : null}
    </Card>
  )
}

export default function DashboardPage() {
  const { t, i18n } = useTranslation()
  const language = i18n.resolvedLanguage ?? i18n.language

  const statusQuery = useQuery({
    queryKey: queryKeys.status,
    queryFn: api.status,
    refetchInterval: 20_000,
  })
  const projectsQuery = useQuery({
    queryKey: queryKeys.projects,
    queryFn: () => api.projects.list(),
    refetchInterval: 30_000,
  })
  const auditQuery = useQuery({
    queryKey: queryKeys.audit(8),
    queryFn: () => api.audit.list(8),
    refetchInterval: 30_000,
  })

  const status = useMemo(
    () => parseStatus(statusQuery.data, language),
    [statusQuery.data, language],
  )
  const projects = useMemo(() => projectsQuery.data ?? [], [projectsQuery.data])
  const environments = useMemo(() => flattenEnvironments(projects), [projects])
  const runningEnvironments = environments.filter((environment) =>
    isRunningStatus(environment.status),
  ).length
  const totalEnvironments = environments.length || status.environments.total || 0
  const runningTotal = environments.length > 0 ? runningEnvironments : (status.environments.running ?? 0)

  const needsHostFallback =
    statusQuery.isSuccess &&
    (status.cpu.percent === null || status.memory.percent === null || status.disk.percent === null)

  const hostFallbackQuery = useQuery({
    queryKey: ['metrics', 'host-overview'] as const,
    queryFn: async () => {
      const [cpu, memory, disk] = await Promise.allSettled([
        api.metrics.query(HOST_QUERIES.cpu),
        api.metrics.query(HOST_QUERIES.memory),
        api.metrics.query(HOST_QUERIES.disk),
      ])
      const read = (result: PromiseSettledResult<unknown>) =>
        result.status === 'fulfilled' ? latestMetricValue(result.value) : null
      return { cpu: read(cpu), memory: read(memory), disk: read(disk) }
    },
    enabled: needsHostFallback,
    refetchInterval: 30_000,
    staleTime: 15_000,
    retry: 1,
  })

  const fallback = hostFallbackQuery.data
  const cpuPercent = status.cpu.percent ?? fallback?.cpu ?? null
  const memoryPercent = status.memory.percent ?? fallback?.memory ?? null
  const diskPercent = status.disk.percent ?? fallback?.disk ?? null

  const hostHint = (metric: HostMetric, fallbackValue: number | null): string => {
    if (metric.detail) return metric.detail
    if (metric.percent !== null) return t('dashboard.hostHint')
    if (fallbackValue !== null) return t('dashboard.hostFallback')
    return t('dashboard.hostUnavailable')
  }

  const auditEvents = useMemo(() => normalizeAuditEvents(auditQuery.data), [auditQuery.data])

  const sortedEnvironments = useMemo(() => {
    const stageRank: Record<string, number> = { dev: 0, staging: 1, prod: 2 }
    return [...environments].sort((a, b) => {
      const runningDelta = Number(isRunningStatus(b.status)) - Number(isRunningStatus(a.status))
      if (runningDelta !== 0) return runningDelta
      const projectDelta = a.project.localeCompare(b.project)
      if (projectDelta !== 0) return projectDelta
      return (stageRank[a.stage] ?? 9) - (stageRank[b.stage] ?? 9)
    })
  }, [environments])

  const isRefreshing =
    statusQuery.isFetching || projectsQuery.isFetching || auditQuery.isFetching

  const refreshAll = () => {
    void Promise.all([statusQuery.refetch(), projectsQuery.refetch(), auditQuery.refetch()])
  }

  return (
    <>
      <PageHeader
        title={t('dashboard.title')}
        description={t('dashboard.subtitle')}
        actions={
          <Button onClick={refreshAll} disabled={isRefreshing}>
            <RotateCw className={cn('h-4 w-4', isRefreshing && 'animate-spin')} aria-hidden="true" />
            {isRefreshing ? t('common.refreshing') : t('common.refresh')}
          </Button>
        }
      />

      {statusQuery.isError ? (
        <ErrorState
          error={statusQuery.error}
          title={t('dashboard.loadError')}
          onRetry={() => void statusQuery.refetch()}
          className="mb-5"
        />
      ) : null}

      <section aria-label={t('dashboard.title')} className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        <StatCard
          label={t('dashboard.projects')}
          value={formatNumber(projects.length, language)}
          hint={t('dashboard.projectsHint')}
          icon={FolderKanban}
          loading={projectsQuery.isLoading}
        />
        <StatCard
          label={t('dashboard.environments')}
          value={`${formatNumber(runningTotal, language)} / ${formatNumber(totalEnvironments, language)}`}
          hint={t('dashboard.environmentsHint', {
            running: formatNumber(runningTotal, language),
            total: formatNumber(totalEnvironments, language),
          })}
          icon={Activity}
          loading={projectsQuery.isLoading && !statusQuery.isSuccess}
        />
        <StatCard
          label={t('dashboard.cpu')}
          value={formatPercent(cpuPercent, language, 0)}
          hint={hostHint(status.cpu, fallback?.cpu ?? null)}
          icon={Cpu}
          percent={cpuPercent}
          loading={statusQuery.isLoading}
        />
        <StatCard
          label={t('dashboard.memory')}
          value={formatPercent(memoryPercent, language, 0)}
          hint={hostHint(status.memory, fallback?.memory ?? null)}
          icon={MemoryStick}
          percent={memoryPercent}
          loading={statusQuery.isLoading}
        />
        <StatCard
          label={t('dashboard.disk')}
          value={formatPercent(diskPercent, language, 0)}
          hint={hostHint(status.disk, fallback?.disk ?? null)}
          icon={HardDrive}
          percent={diskPercent}
          loading={statusQuery.isLoading}
        />
      </section>

      <Card className="mt-4">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2 px-5 py-3 text-xs text-slate-400">
          <span className="inline-flex items-center gap-2">
            <Server className="h-3.5 w-3.5 text-slate-500" aria-hidden="true" />
            {t('dashboard.docker')}
            <Badge
              tone={
                status.docker.online === null
                  ? 'neutral'
                  : status.docker.online
                    ? 'success'
                    : 'danger'
              }
            >
              {status.docker.online === null
                ? t('dashboard.dockerUnknown')
                : status.docker.online
                  ? t('dashboard.dockerOnline')
                  : t('dashboard.dockerOffline')}
            </Badge>
          </span>
          <span>
            {t('dashboard.orchestrator')}
            {status.version ? (
              <span className="ml-1.5 text-slate-200">
                {t('dashboard.orchestratorVersion', { version: status.version })}
              </span>
            ) : (
              <span className="ml-1.5 text-slate-500">{t('common.notAvailable')}</span>
            )}
          </span>
          {status.docker.label ? (
            <span className="truncate text-slate-500">{status.docker.label}</span>
          ) : null}
        </div>
      </Card>

      <div className="mt-6 grid gap-6 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader
            title={t('dashboard.environmentsTitle')}
            description={t('dashboard.environmentsListHint')}
            actions={
              <Link
                to="/projects"
                className="rounded text-xs font-medium text-accent-300 hover:text-accent-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-400"
              >
                {t('common.viewAll')}
              </Link>
            }
          />
          {projectsQuery.isLoading ? (
            <CardContent>
              <LoadingState rows={3} />
            </CardContent>
          ) : projectsQuery.isError ? (
            <CardContent>
              <ErrorState error={projectsQuery.error} onRetry={() => void projectsQuery.refetch()} />
            </CardContent>
          ) : sortedEnvironments.length === 0 ? (
            <CardContent>
              <EmptyState
                icon={FolderKanban}
                title={t('dashboard.noEnvironmentsTitle')}
                description={t('dashboard.noEnvironmentsHint')}
                action={
                  <Link
                    to="/projects"
                    className="inline-flex h-9 items-center rounded-lg border border-edge bg-surface-raised px-3 text-xs font-medium text-slate-200 hover:bg-surface-overlay focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-400"
                  >
                    {t('dashboard.noEnvironmentsAction')}
                  </Link>
                }
              />
            </CardContent>
          ) : (
            <ul className="divide-y divide-edge-muted">
              {sortedEnvironments.map((environment) => (
                <li key={`${environment.project}-${environment.stage}`}>
                  <Link
                    to={`/projects/${encodeURIComponent(environment.project)}/environments/${encodeURIComponent(environment.stage)}`}
                    className="flex items-center gap-3 px-5 py-3 transition-colors hover:bg-surface-raised/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent-400"
                  >
                    <StatusBadge status={environment.status} />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-slate-100">
                        {environment.project}
                      </p>
                      <p className="mt-0.5 text-xs text-slate-500">
                        {t(`stages.${environment.stage}`, { defaultValue: environment.stage })}
                        {' · '}
                        {formatRelativeTime(
                          environment.updated_at ?? environment.created_at,
                          language,
                        )}
                      </p>
                    </div>
                    <ChevronRight className="h-4 w-4 shrink-0 text-slate-600" aria-hidden="true" />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card>
          <CardHeader
            title={t('dashboard.recentEventsTitle')}
            description={t('dashboard.recentEventsHint')}
            actions={
              <Link
                to="/audit"
                className="rounded text-xs font-medium text-accent-300 hover:text-accent-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-400"
              >
                {t('common.viewAll')}
              </Link>
            }
          />
          {auditQuery.isLoading ? (
            <CardContent>
              <LoadingState rows={3} />
            </CardContent>
          ) : auditQuery.isError ? (
            <CardContent>
              <ErrorState error={auditQuery.error} onRetry={() => void auditQuery.refetch()} />
            </CardContent>
          ) : auditEvents.length === 0 ? (
            <CardContent>
              <EmptyState
                icon={ScrollText}
                title={t('dashboard.noEventsTitle')}
                description={t('dashboard.noEventsHint')}
              />
            </CardContent>
          ) : (
            <ul className="divide-y divide-edge-muted">
              {auditEvents.map((event) => (
                <li key={event.id} className="flex items-start gap-3 px-5 py-3">
                  <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-surface-raised text-slate-400">
                    <ScrollText className="h-3.5 w-3.5" aria-hidden="true" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm text-slate-200">
                      {event.action || t('common.unknown')}
                    </p>
                    <p className="mt-0.5 truncate text-xs text-slate-500">
                      {event.actor ?? t('audit.unknownActor')}
                      {event.project
                        ? ` · ${t('audit.projectOnly', { project: event.project })}`
                        : ''}
                      {event.project && event.stage
                        ? ` · ${t(`stages.${event.stage}`, { defaultValue: event.stage })}`
                        : ''}
                    </p>
                    <p className="mt-0.5 text-[11px] text-slate-600">
                      {formatRelativeTime(event.timestamp, language)}
                    </p>
                  </div>
                  {event.status ? <StatusBadge status={event.status} /> : null}
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </>
  )
}
