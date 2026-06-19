import { useTranslation } from 'react-i18next'

import { persistLanguageSelection } from '../i18n'

const LANGUAGES = [
  { code: 'he', labelKey: 'language.hebrew' },
  { code: 'en', labelKey: 'language.english' },
]

function LanguageSwitcher({ className = '' }) {
  const { i18n, t } = useTranslation()
  const currentLanguage = i18n.resolvedLanguage || i18n.language || 'he'

  function handleLanguageChange(event) {
    const nextLanguage = event.target.value
    persistLanguageSelection(nextLanguage)
    i18n.changeLanguage(nextLanguage)
  }

  return (
    <label className={`language-switcher ${className}`.trim()}>
      <span>{t('language.label')}</span>
      <select value={currentLanguage} onChange={handleLanguageChange}>
        {LANGUAGES.map((language) => (
          <option key={language.code} value={language.code}>
            {t(language.labelKey)}
          </option>
        ))}
      </select>
    </label>
  )
}

export default LanguageSwitcher
