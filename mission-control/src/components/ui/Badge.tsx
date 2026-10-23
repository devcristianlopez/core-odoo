import type { HTMLAttributes } from 'react'
import { cn } from '../../lib/utils'

export type BadgeTone = 'success' | 'warning' | 'danger' | 'neutral' | 'info'

const toneClasses: Record<BadgeTone, string> = {
  success: 'bg-success-900/60 text-success-400 ring-success-500/30',
  warning: 'bg-warning-900/60 text-warning-400 ring-warning-500/30',
  danger: 'bg-danger-900/60 text-danger-400 ring-danger-500/30',
  neutral: 'bg-slate-800/70 text-slate-300 ring-slate-600/40',
  info: 'bg-accent-900/50 text-accent-300 ring-accent-500/30',
}

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: BadgeTone
}

export function Badge({ className, tone = 'neutral', ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset',
        toneClasses[tone],
        className,
      )}
      {...props}
    />
  )
}
