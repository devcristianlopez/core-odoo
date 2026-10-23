import { Globe2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { changeLanguage, isLanguage, LANGUAGES, type Language } from '../lib/i18n'
import { cn } from '../lib/utils'

export function LanguageSwitcher({ className }: { className?: string }) {
  const { t, i18n } = useTranslation()
  const current = (i18n.resolvedLanguage ?? i18n.language ?? 'en').split('-')[0]
  const value: Language = isLanguage(current) ? current : 'en'

  return (
    <div className={cn('relative inline-flex items-center', className)}>
      <Globe2
        className="pointer-events-none absolute left-2.5 h-3.5 w-3.5 text-slate-400"
        aria-hidden="true"
      />
      <select
        value={value}
        onChange={(event) => {
          if (isLanguage(event.target.value)) changeLanguage(event.target.value)
        }}
        aria-label={t('common.language')}
        className="h-9 appearance-none rounded-lg border border-edge bg-surface-raised py-0 pl-8 pr-7 text-xs font-medium text-slate-200 transition-colors hover:border-edge-strong focus:border-accent-500 focus:outline-none focus:ring-2 focus:ring-accent-500/30"
      >
        {LANGUAGES.map((language) => (
          <option key={language} value={language}>
            {language === 'en' ? t('settings.english') : t('settings.spanish')}
          </option>
        ))}
      </select>
      <span
        className="pointer-events-none absolute right-2.5 text-[10px] text-slate-500"
        aria-hidden="true"
      >
        ▾
      </span>
    </div>
  )
}
