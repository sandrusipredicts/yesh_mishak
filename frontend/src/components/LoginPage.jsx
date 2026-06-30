import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import {
  loginWithPassword,
  registerWithPassword,
  saveAuthSession,
} from '../api/auth'
import { startGoogleOAuth } from '../oauth'

function LoginPage({ onLogin }) {
  const { t } = useTranslation()
  const [mode, setMode] = useState('login')
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [loginForm, setLoginForm] = useState({
    username: '',
    password: '',
  })
  const [registerForm, setRegisterForm] = useState({
    full_name: '',
    username: '',
    email: '',
    phone_number: '',
    password: '',
    password_confirm: '',
  })
  const handleAuthSuccess = useCallback((authData) => {
    const sessionUser = saveAuthSession(authData)
    onLogin?.(sessionUser)
  }, [onLogin])

  useEffect(() => {
    function handleOAuthError() {
      setIsLoading(false)
      setError(t('auth.googleSignInFailed'))
    }

    window.addEventListener('auth-oauth-error', handleOAuthError)

    return () => {
      window.removeEventListener('auth-oauth-error', handleOAuthError)
    }
  }, [t])

  async function handleGoogleLogin() {
    setIsLoading(true)
    setError('')

    try {
      await startGoogleOAuth()
    } catch {
      setIsLoading(false)
      setError(t('auth.googleSignInFailed'))
    }
  }

  function updateLoginForm(event) {
    const { name, value } = event.target
    setLoginForm((current) => ({ ...current, [name]: value }))
  }

  function updateRegisterForm(event) {
    const { name, value } = event.target
    setRegisterForm((current) => ({ ...current, [name]: value }))
  }

  function getApiErrorMessage(apiError, fallback) {
    const detail = apiError?.response?.data?.detail
    if (typeof detail === 'string') {
      return detail
    }

    if (Array.isArray(detail) && detail.length > 0) {
      return detail[0]?.msg || fallback
    }

    return fallback
  }

  const passwordMismatch =
    mode === 'register' &&
    registerForm.password_confirm.length > 0 &&
    registerForm.password !== registerForm.password_confirm

  async function handlePasswordLogin(event) {
    event.preventDefault()
    setIsLoading(true)
    setError('')

    try {
      const authData = await loginWithPassword(loginForm)
      handleAuthSuccess(authData)
    } catch (apiError) {
      setError(getApiErrorMessage(apiError, t('auth.signInFailed')))
    } finally {
      setIsLoading(false)
    }
  }

  async function handleRegister(event) {
    event.preventDefault()

    if (registerForm.password !== registerForm.password_confirm) {
      setError(t('auth.passwordMismatch'))
      return
    }

    setIsLoading(true)
    setError('')

    try {
      const authData = await registerWithPassword(registerForm)
      handleAuthSuccess(authData)
    } catch (apiError) {
      setError(getApiErrorMessage(apiError, t('auth.accountCreateFailed')))
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <main className="login-page">
      <section className="login-panel" aria-labelledby="login-title">
        <h1 id="login-title">yesh_mishak</h1>
        <p>{t('app.tagline')}</p>

        <div className="auth-mode-tabs" role="tablist" aria-label={t('auth.method')}>
          <button
            type="button"
            role="tab"
            aria-selected={mode === 'login'}
            aria-controls="login-tabpanel"
            id="login-tab"
            className={mode === 'login' ? 'active' : ''}
            onClick={() => {
              setMode('login')
              setError('')
            }}
          >
            {t('auth.login')}
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === 'register'}
            aria-controls="register-tabpanel"
            id="register-tab"
            className={mode === 'register' ? 'active' : ''}
            onClick={() => {
              setMode('register')
              setError('')
            }}
          >
            {t('auth.register')}
          </button>
        </div>

        {mode === 'login' ? (
          <form className="auth-form" role="tabpanel" id="login-tabpanel" aria-labelledby="login-tab" onSubmit={handlePasswordLogin}>
            <label>
              <span>{t('auth.usernameOrEmail')}</span>
              <input
                autoComplete="username"
                name="username"
                onChange={updateLoginForm}
                required
                type="text"
                value={loginForm.username}
              />
            </label>
            <label>
              <span>{t('auth.password')}</span>
              <input
                autoComplete="current-password"
                name="password"
                onChange={updateLoginForm}
                required
                type="password"
                value={loginForm.password}
              />
            </label>
            {error ? <p className="login-error" role="alert">{error}</p> : null}
            <button className="auth-submit" disabled={isLoading} type="submit">
              {t('auth.signIn')}
            </button>
          </form>
        ) : (
          <form className="auth-form" role="tabpanel" id="register-tabpanel" aria-labelledby="register-tab" onSubmit={handleRegister}>
            <label>
              <span>{t('auth.fullName')}</span>
              <input
                autoComplete="name"
                name="full_name"
                onChange={updateRegisterForm}
                required
                type="text"
                value={registerForm.full_name}
              />
            </label>
            <label>
              <span>{t('auth.username')}</span>
              <input
                autoComplete="username"
                minLength={3}
                name="username"
                onChange={updateRegisterForm}
                required
                type="text"
                value={registerForm.username}
              />
            </label>
            <label>
              <span>{t('auth.email')}</span>
              <input
                autoComplete="email"
                name="email"
                onChange={updateRegisterForm}
                required
                type="email"
                value={registerForm.email}
              />
            </label>
            <label>
              <span>{t('auth.phoneNumber')}</span>
              <input
                autoComplete="tel"
                name="phone_number"
                onChange={updateRegisterForm}
                required
                type="tel"
                value={registerForm.phone_number}
              />
            </label>
            <label>
              <span>{t('auth.password')}</span>
              <input
                autoComplete="new-password"
                maxLength={128}
                minLength={8}
                name="password"
                onChange={updateRegisterForm}
                required
                type="password"
                value={registerForm.password}
              />
              <span className="form-hint">{t('auth.passwordHint')}</span>
            </label>
            <label>
              <span>{t('auth.confirmPassword')}</span>
              <input
                autoComplete="new-password"
                maxLength={128}
                minLength={8}
                name="password_confirm"
                onChange={updateRegisterForm}
                required
                type="password"
                value={registerForm.password_confirm}
                aria-describedby={passwordMismatch ? 'error-password-confirm' : undefined}
              />
              {passwordMismatch ? (
                <span className="form-field-error" id="error-password-confirm">{t('auth.passwordMismatch')}</span>
              ) : null}
            </label>
            {error ? <p className="login-error" role="alert">{error}</p> : null}
            <button className="auth-submit" disabled={isLoading || passwordMismatch} type="submit">
              {t('auth.createAccount')}
            </button>
          </form>
        )}

        <div className="auth-divider" aria-hidden="true">
          <span />
          <strong>{t('auth.or')}</strong>
          <span />
        </div>
        <button
          type="button"
          className="google-login-button"
          disabled={isLoading}
          onClick={handleGoogleLogin}
        >
          Google
        </button>
        {isLoading ? <p className="login-status">{t('auth.signingIn')}</p> : null}
      </section>
    </main>
  )
}

export default LoginPage
