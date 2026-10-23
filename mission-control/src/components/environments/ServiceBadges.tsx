import { useTranslation } from 'react-i18next'
import { Badge } from '../ui/Badge'
import { normalizeServices } from '../../lib/services'
import { normalizeStatusKey, statusTone } from '../../lib/status'

export function ServiceBadges({
  services,
  emptyLabel,
}: {
  services: unknown
  emptyLabel: string
}) {
  const { t } = useTranslation()
  const normalized = normalizeServices(services)
  if (normalized.length === 0) {
    return <p className="text-xs text-slate-500">{emptyLabel}</p>
  }
  return (
    <ul className="flex flex-wrap gap-1.5" aria-label={t('common.services')}>
      {normalized.map((service) => {
        const statusLabel = service.status
          ? t(`status.${normalizeStatusKey(service.status)}`, { defaultValue: service.status })
          : null
        return (
          <li key={service.name}>
            <Badge
              tone={service.status ? statusTone(service.status) : 'neutral'}
              aria-label={statusLabel ? `${service.name} — ${statusLabel}` : service.name}
            >
              {service.name}
            </Badge>
          </li>
        )
      })}
    </ul>
  )
}
