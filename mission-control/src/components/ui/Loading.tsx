import { Loader2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { cn } from '../../lib/utils'

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden="true" className={cn('animate-pulse rounded-md bg-surface-raised', className)} />
}

export function LoadingState({
  label,
  className,
  rows = 3,
}: {
  label?: string
  className?: string
  rows?: number
}) {
  const { t } = useTranslation()
  return (
    <div className={cn('rounded-xl border border-edge bg-surface px-5 py-6', className)} role="status">
      <span className="sr-only">{label ?? t('common.loading')}</span>
      <div className="space-y-3" aria-hidden="true">
        {Array.from({ length: rows }).map((_, index) => (
          <div key={index} className="flex items-center gap-3">
            <Skeleton className="h-9 w-9 rounded-full" />
            <div className="flex-1 space-y-2">
              <Skeleton className={index % 2 === 0 ? 'h-3 w-2/3' : 'h-3 w-1/2'} />
              <Skeleton className="h-3 w-1/3" />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export function FullPageLoader({ label }: { label?: string }) {
  const { t } = useTranslation()
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-3" role="status">
      <Loader2 className="h-6 w-6 animate-spin text-accent-400" aria-hidden="true" />
      <p className="text-sm text-slate-400">{label ?? t('common.loading')}</p>
    </div>
  )
}

export function InlineLoader({ label }: { label?: string }) {
  const { t } = useTranslation()
  return (
    <span className="inline-flex items-center gap-2 text-xs text-slate-400" role="status">
      <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
      {label ?? t('common.loading')}
    </span>
  )
}
