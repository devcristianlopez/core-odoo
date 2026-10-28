import { useEffect, useId, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { RotateCw } from 'lucide-react'
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { api } from '../../lib/api'
import { queryKeys } from '../../lib/query'
import { extractMetricPoints, mergeHistory } from '../../lib/metrics'
import { formatBytes, formatDurationSeconds, formatNumber, formatPercent, formatTime } from '../../lib/format'
import type { MetricPoint } from '../../lib/types'
import { Card, CardContent, CardHeader } from '../ui/Card'
import { Button } from '../ui/Button'
import { Skeleton } from '../ui/Loading'
import { describeError } from '../../lib/errors'

export type MetricFormat = 'cores' | 'bytes' | 'seconds' | 'rate' | 'percent'

const colorClasses = {
  accent: { stroke: '#2fb8b1', fill: '#2fb8b1' },
  brand: { stroke: '#a06e90', fill: '#a06e90' },
  warning: { stroke: '#f5b74e', fill: '#f5b74e' },
  danger: { stroke: '#f47676', fill: '#f47676' },
} as const

function formatMetric(value: number, format: MetricFormat, language: string, unitLabel: string): string {
  switch (format) {
    case 'cores':
      return `${formatNumber(value, language, 2)} ${unitLabel}`
    case 'bytes':
      return formatBytes(value, language, 1)
    case 'seconds':
      return formatDurationSeconds(value, language)
    case 'rate':
      return `${formatNumber(value, language, 3)} ${unitLabel}`
    case 'percent':
      return formatPercent(value, language, 0)
  }
}

export function useMetricSeries(
  query: string,
  options: { paused?: boolean; refetchInterval?: number } = {},
) {
  const { paused = false, refetchInterval = 15_000 } = options
  const [history, setHistory] = useState<MetricPoint[]>([])
  const result = useQuery({
    queryKey: queryKeys.metrics(query),
    queryFn: () => api.metrics.query(query),
    refetchInterval: paused ? false : refetchInterval,
    staleTime: 5_000,
    retry: 1,
  })

  useEffect(() => {
    setHistory([])
  }, [query])

  useEffect(() => {
    if (!result.data) return
    const incoming = extractMetricPoints(result.data)
    if (incoming.length === 0) return
    setHistory((previous) => mergeHistory(previous, incoming))
  }, [result.data, result.dataUpdatedAt])

  const latest = history.length > 0 ? (history[history.length - 1]?.value ?? null) : null
  return { ...result, history, latest }
}

export interface MetricChartProps {
  title: string
  description?: string
  query: string
  format: MetricFormat
  unitLabel: string
  color: keyof typeof colorClasses
  paused?: boolean
  className?: string
  emptyLabel?: string
}

export function MetricChart({
  title,
  description,
  query,
  format,
  unitLabel,
  color,
  paused = false,
  emptyLabel,
}: MetricChartProps) {
  const { t, i18n } = useTranslation()
  const language = i18n.resolvedLanguage ?? i18n.language
  const gradientId = `metric-${useId().replace(/[^a-zA-Z0-9_-]/g, '')}`
  const { history, latest, isLoading, isError, error, refetch, isFetching } = useMetricSeries(query, {
    paused,
  })

  const data = useMemo(
    () => history.map((point) => ({ time: point.timestamp, value: point.value })),
    [history],
  )

  const formattedLatest = latest === null ? '—' : formatMetric(latest, format, language, unitLabel)
  const palette = colorClasses[color]

  return (
    <Card>
      <CardHeader
        title={title}
        description={description}
        actions={
          <div className="flex items-center gap-2">
            {isFetching && !isLoading ? (
              <span
                className="h-1.5 w-1.5 animate-pulse-soft rounded-full bg-accent-300"
                aria-hidden="true"
              />
            ) : null}
            <span className="text-lg font-semibold tabular-nums text-white">{formattedLatest}</span>
          </div>
        }
      />
      <CardContent className="pt-3">
        {isLoading ? (
          <Skeleton className="h-40 w-full" />
        ) : isError && history.length === 0 ? (
          <div role="alert" className="flex h-40 flex-col items-center justify-center gap-2 text-center">
            <p className="text-xs text-danger-400">{t('environment.chartError')}</p>
            <p className="max-w-[18rem] text-[11px] text-slate-500">{describeError(error, t)}</p>
            <Button size="sm" variant="ghost" onClick={() => void refetch()}>
              <RotateCw className="h-3.5 w-3.5" aria-hidden="true" />
              {t('common.retry')}
            </Button>
          </div>
        ) : data.length === 0 ? (
          <div className="flex h-40 items-center justify-center px-4 text-center">
            <p className="text-xs text-slate-500">
              {emptyLabel ?? t('environment.chartEmpty')}
            </p>
          </div>
        ) : (
          <figure aria-label={title}>
            <p className="sr-only">
              {t('environment.currentValue')}: {formattedLatest}
            </p>
            <div className="h-40" aria-hidden="true">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: -18 }}>
                  <defs>
                    <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={palette.fill} stopOpacity={0.35} />
                      <stop offset="100%" stopColor={palette.fill} stopOpacity={0.02} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="#1e2531" strokeDasharray="3 3" vertical={false} />
                  <XAxis
                    dataKey="time"
                    tickFormatter={(value: number) => formatTime(value, language)}
                    tick={{ fill: '#64748b', fontSize: 10 }}
                    axisLine={false}
                    tickLine={false}
                    minTickGap={32}
                  />
                  <YAxis
                    tick={{ fill: '#64748b', fontSize: 10 }}
                    axisLine={false}
                    tickLine={false}
                    width={44}
                    tickFormatter={(value: number) => {
                      if (format === 'bytes') return formatBytes(value, language, 0)
                      if (format === 'percent') return formatPercent(value, language, 0)
                      return formatNumber(value, language, 2)
                    }}
                  />
                  <Tooltip
                    contentStyle={{
                      background: '#161d27',
                      border: '1px solid #28303d',
                      borderRadius: 10,
                      fontSize: 12,
                    }}
                    labelStyle={{ color: '#94a3b8' }}
                    itemStyle={{ color: '#e2e8f0' }}
                    labelFormatter={(label) => formatTime(Number(label), language)}
                    formatter={(value) => [
                      formatMetric(Number(value), format, language, unitLabel),
                      title,
                    ]}
                  />
                  <Area
                    type="monotone"
                    dataKey="value"
                    stroke={palette.stroke}
                    strokeWidth={2}
                    fill={`url(#${gradientId})`}
                    isAnimationActive={false}
                    dot={data.length < 3 ? { r: 2, fill: palette.stroke } : false}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
            <figcaption className="mt-2 flex items-center justify-between text-[11px] text-slate-500">
              <span>{description ?? t('environment.metricsHint')}</span>
              {data.length > 0 ? (
                <span>{formatTime(data[0]?.time ?? 0, language)} — {formatTime(data[data.length - 1]?.time ?? 0, language)}</span>
              ) : null}
            </figcaption>
          </figure>
        )}
      </CardContent>
    </Card>
  )
}
