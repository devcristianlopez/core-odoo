import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { AlertCircle, CheckCircle2, Info, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { cn } from '../lib/utils'
import {
  ToastContext,
  type ToastContextValue,
  type ToastInput,
  type ToastVariant,
} from '../lib/toast-context'

interface ToastRecord extends ToastInput {
  id: string
  variant: ToastVariant
}

let toastCounter = 0

function createToastId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  toastCounter += 1
  return `toast-${Date.now()}-${toastCounter}`
}

const variantClasses: Record<ToastVariant, string> = {
  success: 'border-success-500/40 bg-surface-raised',
  error: 'border-danger-500/50 bg-surface-raised',
  info: 'border-accent-500/40 bg-surface-raised',
}

const iconClasses: Record<ToastVariant, string> = {
  success: 'text-success-400',
  error: 'text-danger-400',
  info: 'text-accent-300',
}

const icons = {
  success: CheckCircle2,
  error: AlertCircle,
  info: Info,
} as const

export function ToastProvider({ children }: { children: ReactNode }) {
  const { t } = useTranslation()
  const [toasts, setToasts] = useState<ToastRecord[]>([])
  const timers = useRef(new Map<string, number>())

  const dismissToast = useCallback((id: string) => {
    const timer = timers.current.get(id)
    if (timer !== undefined) {
      window.clearTimeout(timer)
      timers.current.delete(id)
    }
    setToasts((current) => current.filter((toast) => toast.id !== id))
  }, [])

  const pushToast = useCallback(
    (input: ToastInput) => {
      const id = createToastId()
      const toast: ToastRecord = { ...input, id, variant: input.variant ?? 'info' }
      setToasts((current) => [...current.slice(-3), toast])
      const duration = input.durationMs ?? 5000
      if (duration > 0) {
        const timer = window.setTimeout(() => dismissToast(id), duration)
        timers.current.set(id, timer)
      }
    },
    [dismissToast],
  )

  useEffect(() => {
    const pending = timers.current
    return () => {
      for (const timer of pending.values()) window.clearTimeout(timer)
      pending.clear()
    }
  }, [])

  const value = useMemo<ToastContextValue>(
    () => ({ pushToast, dismissToast }),
    [pushToast, dismissToast],
  )

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        role="region"
        aria-label={t('toast.region')}
        aria-live="polite"
        className="pointer-events-none fixed inset-x-0 bottom-0 z-[60] flex flex-col items-center gap-2 p-4 sm:inset-x-auto sm:right-0 sm:items-end"
      >
        {toasts.map((toast) => {
          const Icon = icons[toast.variant]
          return (
            <div
              key={toast.id}
              role={toast.variant === 'error' ? 'alert' : 'status'}
              className={cn(
                'pointer-events-auto flex w-full max-w-sm items-start gap-3 rounded-xl border px-4 py-3 shadow-2xl',
                'animate-slide-in-right',
                variantClasses[toast.variant],
              )}
            >
              <Icon className={cn('mt-0.5 h-5 w-5 shrink-0', iconClasses[toast.variant])} aria-hidden="true" />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-white">{toast.title}</p>
                {toast.description ? (
                  <p className="mt-0.5 break-words text-xs text-slate-400">{toast.description}</p>
                ) : null}
              </div>
              <button
                type="button"
                onClick={() => dismissToast(toast.id)}
                aria-label={t('toast.dismiss')}
                className="rounded-md p-1 text-slate-500 transition-colors hover:bg-surface-overlay hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-400"
              >
                <X className="h-3.5 w-3.5" aria-hidden="true" />
              </button>
            </div>
          )
        })}
      </div>
    </ToastContext.Provider>
  )
}
