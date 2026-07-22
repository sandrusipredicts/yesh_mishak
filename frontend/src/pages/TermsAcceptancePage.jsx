import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { acceptTerms } from '../api/auth'

function TermsAcceptancePage({ onAccepted }) {
  const { t } = useTranslation()
  const [agreed, setAgreed] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit(event) {
    event.preventDefault()
    if (!agreed || isSaving) return
    setIsSaving(true)
    setError('')
    try {
      await acceptTerms()
      onAccepted()
    } catch {
      setError(t('termsAcceptance.failed'))
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <main className="login-page">
      <section className="login-panel terms-acceptance-panel" aria-labelledby="terms-acceptance-title">
        <h1 id="terms-acceptance-title">{t('termsAcceptance.title')}</h1>
        <p>{t('termsAcceptance.description')}</p>
        <p>{t('termsAcceptance.communityRules')}</p>
        <form className="auth-form" onSubmit={handleSubmit}>
          <label className="terms-consent-label">
            <input
              checked={agreed}
              onChange={(event) => setAgreed(event.target.checked)}
              type="checkbox"
            />
            <span>
              {t('termsAcceptance.agreePrefix')}{' '}
              <a href="/terms" target="_blank" rel="noreferrer">{t('termsAcceptance.termsLink')}</a>
              {' '}{t('termsAcceptance.and')}{' '}
              <a href="/privacy" target="_blank" rel="noreferrer">{t('termsAcceptance.privacyLink')}</a>.
            </span>
          </label>
          {error ? <p className="login-error" role="alert">{error}</p> : null}
          <button className="auth-submit" disabled={!agreed || isSaving} type="submit">
            {isSaving ? t('termsAcceptance.saving') : t('termsAcceptance.continue')}
          </button>
        </form>
      </section>
    </main>
  )
}

export default TermsAcceptancePage
