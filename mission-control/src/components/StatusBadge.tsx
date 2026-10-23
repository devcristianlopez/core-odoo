import { useTranslation } from 'react-i18next'
import { Badge, type BadgeTone } from './ui/Badge'
import { normalizeStatusKey, statusTone } from '../lib/status'

const dotClasses: Record<BadgeTone, string> = {
  success: 'bg-success-400',
  warning: 'bg-warning-400',
  danger: 'bg-danger-400',
  neutral: 'bg-slate-400',
  info: 'bg-accent-300',
}

export function StatusBadge({ status, className }: { status: unknown; className?: string }) {
  const { t } = useTranslation()
  const key = normalizeStatusKey(status)
  const raw = typeof status === 'string' && status.trim() !== '' ? status : undefined
  const label = t(`status.${key}`, { defaultValue: raw ?? t('common.unknown') })
  const tone = statusTone(status)
  return (
    <Badge tone={tone} className={className}>
      <span className={`h-1.5 w-1.5 rounded-full ${dotClasses[tone]}`} aria-hidden="true" />
      {label}
    </Badge>
  )
}
