import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import en from '../i18n/en'
import es from '../i18n/es'

export const LANGUAGES = ['en', 'es'] as const
export type Language = (typeof LANGUAGES)[number]
export const LANGUAGE_STORAGE_KEY = 'core-odoo.lang'

export function isLanguage(value: unknown): value is Language {
  return typeof value === 'string' && (LANGUAGES as readonly string[]).includes(value)
}

/** Stored preference first, then the browser's languages, then English. */
export function detectLanguage(): Language {
  try {
    const stored = window.localStorage.getItem(LANGUAGE_STORAGE_KEY)
    if (isLanguage(stored)) return stored
  } catch {
    // Ignore storage restrictions.
  }
  const candidates =
    typeof navigator === 'undefined'
      ? []
      : [...(Array.isArray(navigator.languages) ? navigator.languages : []), navigator.language]
  for (const candidate of candidates) {
    if (typeof candidate !== 'string') continue
    const base = candidate.toLowerCase().split('-')[0]
    if (base === 'es') return 'es'
    if (base === 'en') return 'en'
  }
  return 'en'
}

export function applyDocumentLanguage(language: string): void {
  if (typeof document !== 'undefined') {
    document.documentElement.lang = language
  }
}

let initialized = false

export function initI18n(): typeof i18n {
  if (initialized) return i18n
  initialized = true
  const language = detectLanguage()
  void i18n.use(initReactI18next).init({
    resources: {
      en: { translation: en },
      es: { translation: es },
    },
    lng: language,
    fallbackLng: 'en',
    supportedLngs: [...LANGUAGES],
    initImmediate: false,
    interpolation: { escapeValue: false },
    returnNull: false,
  })
  applyDocumentLanguage(language)
  i18n.on('languageChanged', (nextLanguage) => {
    applyDocumentLanguage(nextLanguage)
    try {
      window.localStorage.setItem(LANGUAGE_STORAGE_KEY, nextLanguage)
    } catch {
      // Ignore storage restrictions.
    }
  })
  return i18n
}

export function changeLanguage(language: Language): void {
  void i18n.changeLanguage(language)
}

export default i18n
