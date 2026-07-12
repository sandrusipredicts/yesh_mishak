import { Eye, EyeOff } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { confirmPasswordReset } from '../api/auth'
import { clearSession } from '../api/sessionStorage'
import { getPasswordValidationError, PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH } from '../utils/passwordValidation'

function getResetErrorKey(error) {
  const status = error?.response?.status
  const code = error?.response?.data?.code || error?.response?.data?.detail?.code

  if (status === 429 || code === 'RATE_LIMITED') {
    return 'auth.passwordResetRateLimited'
  }

  if (code === 'RESET_TOKEN_EXPIRED') {
    return 'auth.passwordResetExpired'
  }

  if (code === 'RESET_TOKEN_INVALID' || code === 'RESET_TOKEN_CONSUMED') {
    return 'auth.passwordResetInvalid'
  }

  return 'auth.passwordResetGenericError'
}

function PasswordInput({ autoComplete, id, label, name, onChange, value }) {
  const { t } = useTranslation()
  const [isVisible, setIsVisible] = useState(false)

  return (
    <label>
      <span>{label}</span>
      <span className="password-input-wrap">
        <input
          autoComplete={autoComplete}
          id={id}
          maxLength={PASSWORD_MAX_LENGTH}
          minLength={PASSWORD_MIN_LENGTH}
          name={name}
          onChange={onChange}
          required
          type={isVisible ? 'text' : 'password'}
          value={value}
        />
        <button
          aria-label={isVisible ? t('auth.hidePassword') : t('auth.showPassword')}
          className="password-visibility-button"
          onClick={() => setIsVisible((current) => !current)}
          type="button"
        >
          {isVisible ? <EyeOff size={18} aria-hidden="true" /> : <Eye size={18} aria-hidden="true" />}
        </button>
      </span>
    </label>
  )
}

function ResetPasswordPage({ onDone }) {
  const { t } = useTranslation()
  const token = useMemo(() => new URLSearchParams(window.location.search).get('token') || '', [])
  const [form, setForm] = useState({ password: '', password_confirm: '' })
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState(token ? '' : t('auth.passwordResetMissingToken'))
  const [successMessage, setSuccessMessage] = useState('')

  const passwordError = getPasswordValidationError(form.password, t)
  const passwordMismatch = form.password_confirm.length > 0 && form.password !== form.password_confirm
  const canSubmit = Boolean(token) && !isLoading && !passwordError && !passwordMismatch

  function updateForm(event) {
    const { name, value } = event.target
    setForm((current) => ({ ...current, [name]: value }))
  }

  async function handleSubmit(event) {
    event.preventDefault()

    if (!canSubmit) {
      if (!token) {
        setError(t('auth.passwordResetMissingToken'))
      } else if (passwordError) {
        setError(passwordError)
      } else if (passwordMismatch) {
        setError(t('auth.passwordMismatch'))
      }
      return
    }

    setIsLoading(true)
    setError('')
    setSuccessMessage('')

    try {
      await confirmPasswordReset({
        token,
        password: form.password,
        password_confirm: form.password_confirm,
      })

      try {
        await clearSession()
      } catch {
        // clearSession already removes web auth state synchronously before a
        // secure-storage delete can fail. Continue to login without exposing
        // implementation details or the reset token.
      }

      window.history.replaceState(null, '', '/login?reset=success')
      setSuccessMessage(t('auth.passwordResetSuccess'))
      onDone?.(t('auth.passwordResetSuccess'))
    } catch (apiError) {
      setError(t(getResetErrorKey(apiError)))
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <main className="login-page">
      <section className="login-panel" aria-labelledby="reset-password-title">
        <h1 id="reset-password-title">{t('auth.resetPasswordTitle')}</h1>
        <p>{t('auth.resetPasswordDescription')}</p>

        <form className="auth-form" onSubmit={handleSubmit}>
          <PasswordInput
            autoComplete="new-password"
            id="reset-password"
            label={t('auth.newPassword')}
            name="password"
            onChange={updateForm}
            value={form.password}
          />
          <span className="form-hint">{t('auth.passwordHint')}</span>
          {form.password && passwordError ? (
            <span className="form-field-error" role="alert">{passwordError}</span>
          ) : null}

          <PasswordInput
            autoComplete="new-password"
            id="reset-password-confirm"
            label={t('auth.confirmPassword')}
            name="password_confirm"
            onChange={updateForm}
            value={form.password_confirm}
          />
          {passwordMismatch ? (
            <span className="form-field-error" role="alert">{t('auth.passwordMismatch')}</span>
          ) : null}

          {error ? <p className="login-error" role="alert">{error}</p> : null}
          {successMessage ? <p className="login-info" role="status">{successMessage}</p> : null}

          <button className="auth-submit" disabled={!canSubmit} type="submit">
            {isLoading ? t('auth.resettingPassword') : t('auth.resetPasswordAction')}
          </button>
        </form>
      </section>
    </main>
  )
}

export default ResetPasswordPage
