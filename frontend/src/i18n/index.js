import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

import en from '../locales/en/common'
import he from '../locales/he/common'

export const LANGUAGE_STORAGE_KEY = 'app_language'
export const LANGUAGE_SELECTED_STORAGE_KEY = 'language_selected'
export const SUPPORTED_LANGUAGES = ['he', 'en']
export const LANGUAGE_DIRECTIONS = {
  he: 'rtl',
  en: 'ltr',
}

export function normalizeLanguage(language) {
  const normalizedLanguage = String(language || '').toLowerCase()

  if (normalizedLanguage.startsWith('he')) {
    return 'he'
  }

  if (normalizedLanguage.startsWith('en')) {
    return 'en'
  }

  return ''
}

function detectInitialLanguage() {
  if (typeof localStorage !== 'undefined') {
    const storedLanguage = normalizeLanguage(localStorage.getItem(LANGUAGE_STORAGE_KEY))
    if (storedLanguage) {
      return storedLanguage
    }
  }

  if (typeof navigator !== 'undefined') {
    const browserLanguages = [
      ...(Array.isArray(navigator.languages) ? navigator.languages : []),
      navigator.language,
    ]

    for (const browserLanguage of browserLanguages) {
      const normalizedLanguage = normalizeLanguage(browserLanguage)
      if (normalizedLanguage) {
        return normalizedLanguage
      }
    }
  }

  return 'he'
}

export function applyDocumentLanguage(language) {
  const normalizedLanguage = normalizeLanguage(language) || 'he'
  const direction = LANGUAGE_DIRECTIONS[normalizedLanguage]

  document.documentElement.lang = normalizedLanguage
  document.documentElement.dir = direction
  document.body.dir = direction
}

export function hasSelectedLanguage() {
  if (typeof localStorage === 'undefined') {
    return false
  }

  if (localStorage.getItem(LANGUAGE_SELECTED_STORAGE_KEY) === 'true') {
    return true
  }

  if (normalizeLanguage(localStorage.getItem(LANGUAGE_STORAGE_KEY))) {
    localStorage.setItem(LANGUAGE_SELECTED_STORAGE_KEY, 'true')
    return true
  }

  return false
}

export function persistLanguageSelection(language) {
  const normalizedLanguage = normalizeLanguage(language) || 'he'
  localStorage.setItem(LANGUAGE_STORAGE_KEY, normalizedLanguage)
  localStorage.setItem(LANGUAGE_SELECTED_STORAGE_KEY, 'true')
  applyDocumentLanguage(normalizedLanguage)
}

i18n
  .use(initReactI18next)
  .init({
    resources: {
      en: { common: en },
      he: { common: he },
    },
    lng: detectInitialLanguage(),
    fallbackLng: 'he',
    supportedLngs: SUPPORTED_LANGUAGES,
    ns: ['common'],
    defaultNS: 'common',
    interpolation: {
      escapeValue: false,
    },
  })

applyDocumentLanguage(i18n.language)

i18n.on('languageChanged', (language) => {
  const normalizedLanguage = normalizeLanguage(language) || 'he'
  localStorage.setItem(LANGUAGE_STORAGE_KEY, normalizedLanguage)
  applyDocumentLanguage(normalizedLanguage)
})

export default i18n
