import { useTranslation } from 'react-i18next'

import { persistLanguageSelection } from '../i18n'

const LANGUAGE_OPTIONS = [
  { code: 'he', nativeLabel: 'עברית', helperKey: 'language.hebrewHelper' },
  { code: 'en', nativeLabel: 'English', helperKey: 'language.englishHelper' },
]

function LanguageSelectionScreen({ onSelected }) {
  const { i18n, t } = useTranslation()

  async function handleSelect(language) {
    persistLanguageSelection(language)
    await i18n.changeLanguage(language)
    onSelected?.()
  }

  return (
    <main className="language-selection-page">
      <section className="language-selection-panel" aria-labelledby="language-selection-title">
        <h1 id="language-selection-title">{t('language.chooseTitle')}</h1>
        <p>{t('language.chooseSubtitle')}</p>

        <div className="language-selection-options" role="group" aria-label={t('language.label')}>
          {LANGUAGE_OPTIONS.map((language) => (
            <button
              key={language.code}
              type="button"
              className="language-selection-option"
              onClick={() => handleSelect(language.code)}
            >
              <strong>{language.nativeLabel}</strong>
              <span>{t(language.helperKey)}</span>
            </button>
          ))}
        </div>
      </section>
    </main>
  )
}

export default LanguageSelectionScreen
