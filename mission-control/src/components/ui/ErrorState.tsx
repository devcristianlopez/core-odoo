import { AlertTriangle, RotateCw } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { describeError } from '../../lib/errors'
import { Button } from './Button'
import { cn } from '../../lib/utils'

export function ErrorState({
  error,
  onRetry,
  title,
  className,
}: {
  error: unknown
  onRetry?: () => void
  title?: string
  className?: string
}) {
  const { t } = useTranslation()
  return (
    <div
      role="alert"
      className={cn(
        'flex flex-col items-start gap-3 rounded-xl border border-danger-500/30 bg-danger-900/20 px-5 py-4 sm:flex-row sm:items-center',
        className,
      )}
    >
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-danger-900/60 text-danger-400">
        <AlertTriangle className="h-4 w-4" aria-hidden="true" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-white">{title ?? t('errors.loadFailed')}</p>
        <p className="mt-0.5 break-words text-sm text-slate-400">{describeError(error, t)}</p>
      </div>
      {onRetry ? (
        <Button variant="secondary" size="sm" onClick={onRetry} className="shrink-0">
          <RotateCw className="h-3.5 w-3.5" aria-hidden="true" />
          {t('common.retry')}
        </Button>
      ) : null}
    </div>
  )
}
