import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { ChevronDown, ChevronUp, RotateCw, ScrollText, Search } from 'lucide-react'
import { api } from '../lib/api'
import { queryKeys } from '../lib/query'
import { normalizeAuditEvents } from '../lib/audit'
import { formatDateTime, formatRelativeTime } from '../lib/format'
import { PageHeader } from '../components/ui/PageHeader'
import { Card } from '../components/ui/Card'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Input } from '../components/ui/Input'
import { EmptyState } from '../components/ui/EmptyState'
import { ErrorState } from '../components/ui/ErrorState'
import { LoadingState } from '../components/ui/Loading'
import { StatusBadge } from '../components/StatusBadge'
import type { NormalizedAuditEvent } from '../lib/types'

const AUDIT_LIMIT = 100

function eventMatches(event: NormalizedAuditEvent, query: string): boolean {
  const needle = query.trim().toLowerCase()
  if (needle === '') return true
  return [event.action, event.actor, event.project, event.stage, event.status, event.detail]
    .filter((value): value is string => typeof value === 'string')
    .some((value) => value.toLowerCase().includes(needle))
}

export default function AuditPage() {
  const { t, i18n } = useTranslation()
  const language = i18n.resolvedLanguage ?? i18n.language
  const [search, setSearch] = useState('')
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  const auditQuery = useQuery({
    queryKey: queryKeys.audit(AUDIT_LIMIT),
    queryFn: () => api.audit.list(AUDIT_LIMIT),
    refetchInterval: 30_000,
  })

  const events = useMemo(() => normalizeAuditEvents(auditQuery.data), [auditQuery.data])
  const filteredEvents = useMemo(
    () => events.filter((event) => eventMatches(event, search)),
    [events, search],
  )

  const toggleExpanded = (id: string) => {
    setExpanded((current) => {
      const next = new Set(current)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  return (
    <>
      <PageHeader
        title={t('audit.title')}
        description={t('audit.subtitle')}
        actions={
          <>
            <Badge tone="neutral">{t('audit.limit', { limit: AUDIT_LIMIT })}</Badge>
            <Button onClick={() => void auditQuery.refetch()} disabled={auditQuery.isFetching}>
              <RotateCw
                className={auditQuery.isFetching ? 'h-4 w-4 animate-spin' : 'h-4 w-4'}
                aria-hidden="true"
              />
              {auditQuery.isFetching ? t('common.refreshing') : t('common.refresh')}
            </Button>
          </>
        }
      />

      <div className="mb-4 max-w-md">
        <label htmlFor="audit-search" className="sr-only">
          {t('common.search')}
        </label>
        <div className="relative">
          <Search
            className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500"
            aria-hidden="true"
          />
          <Input
            id="audit-search"
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder={t('audit.searchPlaceholder')}
            className="pl-9"
          />
        </div>
      </div>

      {auditQuery.isError ? (
        <ErrorState
          error={auditQuery.error}
          title={t('audit.loadError')}
          onRetry={() => void auditQuery.refetch()}
        />
      ) : auditQuery.isLoading ? (
        <LoadingState rows={6} />
      ) : events.length === 0 ? (
        <EmptyState
          icon={ScrollText}
          title={t('audit.emptyTitle')}
          description={t('audit.emptyDescription')}
        />
      ) : filteredEvents.length === 0 ? (
        <EmptyState
          icon={Search}
          title={t('audit.noMatchTitle')}
          description={t('audit.noMatchDescription')}
        />
      ) : (
        <Card>
          <ul className="divide-y divide-edge-muted">
            {filteredEvents.map((event) => {
              const isExpanded = expanded.has(event.id)
              const target = event.project
                ? event.stage
                  ? t('audit.targetValue', {
                      project: event.project,
                      stage: t(`stages.${event.stage}`, { defaultValue: event.stage }),
                    })
                  : t('audit.projectOnly', { project: event.project })
                : null
              const detailId = `audit-detail-${event.id.replace(/[^a-zA-Z0-9_-]/g, '-')}`
              return (
                <li key={event.id} className="px-5 py-4">
                  <div className="flex items-start gap-3">
                    <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-surface-raised text-slate-400">
                      <ScrollText className="h-4 w-4" aria-hidden="true" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                        <p className="text-sm font-medium text-slate-100">
                          {event.action || t('common.unknown')}
                        </p>
                        {event.status ? <StatusBadge status={event.status} /> : null}
                        <time
                          dateTime={event.timestamp ?? undefined}
                          className="text-[11px] text-slate-500"
                        >
                          {formatRelativeTime(event.timestamp, language)}
                        </time>
                      </div>
                      <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-slate-500">
                        <span>{event.actor ?? t('audit.unknownActor')}</span>
                        {target ? (
                          <>
                            <span aria-hidden="true">·</span>
                            <span>{target}</span>
                          </>
                        ) : null}
                        <span aria-hidden="true">·</span>
                        <span>{formatDateTime(event.timestamp, language)}</span>
                      </p>
                      {event.detail ? (
                        <>
                          <button
                            type="button"
                            onClick={() => toggleExpanded(event.id)}
                            aria-expanded={isExpanded}
                            aria-controls={detailId}
                            className="mt-1.5 inline-flex items-center gap-1 rounded text-[11px] font-medium text-accent-300 hover:text-accent-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-400"
                          >
                            {isExpanded ? (
                              <ChevronUp className="h-3 w-3" aria-hidden="true" />
                            ) : (
                              <ChevronDown className="h-3 w-3" aria-hidden="true" />
                            )}
                            {isExpanded ? t('audit.hideDetails') : t('audit.showDetails')}
                          </button>
                          {isExpanded ? (
                            <pre
                              id={detailId}
                              tabIndex={0}
                              className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-lg border border-edge bg-surface-muted p-3 font-mono text-[11px] text-slate-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-500"
                            >
                              {event.detail}
                            </pre>
                          ) : null}
                        </>
                      ) : null}
                    </div>
                  </div>
                </li>
              )
            })}
          </ul>
        </Card>
      )}
    </>
  )
}
