import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { requestPasswordReset } from '../api/auth'

function isRateLimitError(error) {
  return error?.response?.status === 429 || error?.response?.data?.code === 'RATE_LIMITED'
}

function ForgotPasswordPage({ onBackToLogin }) {
  const { t } = useTranslation()
  const [email, setEmail] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')
  const [successMessage, setSuccessMessage] = useState('')

  async function handleSubmit(event) {
    event.preventDefault()

    if (isLoading) {
      return
    }

    setIsLoading(true)
    setError('')
    setSuccessMessage('')

    try {
      await requestPasswordReset({ email })
      setSuccessMessage(t('auth.passwordResetRequestSuccess'))
    } catch (apiError) {
      if (isRateLimitError(apiError)) {
        setError(t('auth.passwordResetRateLimited'))
      } else {
        setSuccessMessage(t('auth.passwordResetRequestSuccess'))
      }
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <main className="login-page">
      <section className="login-panel" aria-labelledby="forgot-password-title">
        <h1 id="forgot-password-title">{t('auth.forgotPasswordTitle')}</h1>
        <p>{t('auth.forgotPasswordDescription')}</p>

        <form className="auth-form" onSubmit={handleSubmit}>
          <label>
            <span>{t('auth.email')}</span>
            <input
              autoComplete="email"
              name="email"
              onChange={(event) => setEmail(event.target.value)}
              required
              type="email"
              value={email}
            />
          </label>

          {error ? <p className="login-error" role="alert">{error}</p> : null}
          {successMessage ? <p className="login-info" role="status">{successMessage}</p> : null}

          <button className="auth-submit" disabled={isLoading} type="submit">
            {isLoading ? t('auth.sendingResetLink') : t('auth.sendResetLink')}
          </button>
        </form>

        <button className="auth-link-button" type="button" onClick={onBackToLogin}>
          {t('auth.backToLogin')}
        </button>
      </section>
    </main>
  )
}

export default ForgotPasswordPage
