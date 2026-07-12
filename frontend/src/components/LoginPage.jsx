import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import {
  loginWithGoogle,
  loginWithPassword,
  resendVerificationEmail,
  registerWithPassword,
  saveAuthSession,
  verifyEmail,
} from '../api/auth'
import {
  initNativeGoogleAuth,
  signInWithGoogleNative,
} from '../api/nativeGoogleAuth'
import { mapNativeAuthError } from '../api/authErrorMapping'
import { clearSession, isNativeRuntime } from '../api/sessionStorage'

const GOOGLE_SCRIPT_SRC = 'https://accounts.google.com/gsi/client'
let googleScriptPromise

function loadGoogleScript() {
  if (window.google?.accounts?.id) {
    return Promise.resolve()
  }

  if (googleScriptPromise) {
    return googleScriptPromise
  }

  const existingScript = document.querySelector(`script[src="${GOOGLE_SCRIPT_SRC}"]`)
  if (existingScript) {
    googleScriptPromise = new Promise((resolve, reject) => {
      existingScript.addEventListener('load', resolve, { once: true })
      existingScript.addEventListener('error', reject, { once: true })
    })
    return googleScriptPromise
  }

  googleScriptPromise = new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.src = GOOGLE_SCRIPT_SRC
    script.async = true
    script.defer = true
    script.onload = resolve
    script.onerror = reject
    document.head.appendChild(script)
  })

  return googleScriptPromise
}

function LoginPage({ onLogin }) {
  const { t } = useTranslation()
  const initialVerificationToken = (
    window.location.pathname === '/verify-email'
      ? new URLSearchParams(window.location.search).get('token') || ''
      : ''
  )
  const buttonRef = useRef(null)
  const [mode, setMode] = useState(initialVerificationToken ? 'verification' : 'login')
  const [error, setError] = useState('')
  const [nativeAuthFeedback, setNativeAuthFeedback] = useState(null)
  const [isLoading, setIsLoading] = useState(false)
  const [nativeGoogleStatus, setNativeGoogleStatus] = useState('pending')
  const [verificationEmail, setVerificationEmail] = useState('')
  const [verificationMessage, setVerificationMessage] = useState('')
  const [verificationStatus, setVerificationStatus] = useState(
    initialVerificationToken ? 'verifying' : 'idle',
  )
  const [resendCooldown, setResendCooldown] = useState(0)
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
  const googleClientId = import.meta.env.VITE_GOOGLE_CLIENT_ID

  useEffect(() => {
    if (!initialVerificationToken) {
      return
    }

    let active = true
    verifyEmail(initialVerificationToken)
      .then((result) => {
        if (!active) return
        setVerificationStatus(result.status)
      })
      .catch(() => {
        if (!active) return
        setVerificationStatus('invalid')
      })
    return () => { active = false }
  }, [initialVerificationToken])

  useEffect(() => {
    if (resendCooldown <= 0) return undefined
    const timer = window.setInterval(() => {
      setResendCooldown((value) => Math.max(0, value - 1))
    }, 1000)
    return () => window.clearInterval(timer)
  }, [resendCooldown])

  const handleAuthSuccess = useCallback(async (authData) => {
    const sessionUser = await saveAuthSession(authData)
    onLogin?.(sessionUser)
  }, [onLogin])

  useEffect(() => {
    let isMounted = true

    // Native runtime (ISSUE-240): Google sign-in goes through the Android
    // Credential Manager plugin — the GIS web script is never loaded (it does
    // not work inside the WebView, see docs/authentication-flow-audit.md).
    async function initializeNativeGoogleLogin() {
      if (!googleClientId) {
        setNativeGoogleStatus('unavailable')
        setError(t('auth.googleMissingClient'))
        return
      }

      try {
        await initNativeGoogleAuth(googleClientId)

        if (isMounted) {
          setNativeGoogleStatus('ready')
        }
      } catch {
        // Fail closed to "unavailable": manual login stays fully usable.
        if (isMounted) {
          setNativeGoogleStatus('unavailable')
        }
      }
    }

    async function initializeGoogleLogin() {
      if (!googleClientId) {
        setError(t('auth.googleMissingClient'))
        return
      }

      try {
        await loadGoogleScript()

        if (!isMounted) {
          return
        }

        if (!window.google?.accounts?.id) {
          setError(t('auth.googleNotReady'))
          return
        }

        if (!buttonRef.current) {
          setError(t('auth.googleButtonMountFailed'))
          return
        }

        window.google.accounts.id.initialize({
          client_id: googleClientId,
          callback: async (response) => {
            if (!response.credential) {
              setError(t('auth.googleNoCredential'))
              return
            }

            setIsLoading(true)
            setError('')

            try {
              const authData = await loginWithGoogle(response.credential)
              await handleAuthSuccess(authData)
            } catch (apiError) {
              const detail = apiError?.response?.data?.detail
              if (apiError?.response?.status === 409 && detail?.code === 'ACCOUNT_LINKING_REQUIRED') {
                setError(t('auth.accountLinkingRequired'))
              } else {
                setError(t('auth.googleSignInFailed'))
              }
            } finally {
              setIsLoading(false)
            }
          },
        })

        buttonRef.current.innerHTML = ''
        window.google.accounts.id.renderButton(buttonRef.current, {
          theme: 'outline',
          size: 'large',
          width: 280,
        })

        window.setTimeout(() => {
          if (isMounted && buttonRef.current && buttonRef.current.childElementCount === 0) {
            setError(t('auth.googleRenderFailed'))
          }
        }, 0)
      } catch {
        if (isMounted) {
          setError(t('auth.googleLoadFailed'))
        }
      }
    }

    if (isNativeRuntime()) {
      initializeNativeGoogleLogin()
    } else {
      initializeGoogleLogin()
    }

    return () => {
      isMounted = false
    }
  }, [googleClientId, handleAuthSuccess, t])

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
      if (authData.email_verification_required) {
        setVerificationEmail(authData.user?.email || loginForm.username.trim().toLowerCase())
        setVerificationStatus('sent')
        setMode('verification')
      } else {
        await handleAuthSuccess(authData)
      }
    } catch (apiError) {
      const code = apiError?.response?.data?.code
      if (code === 'EMAIL_NOT_VERIFIED') {
        setVerificationEmail(loginForm.username.trim().toLowerCase())
        setVerificationStatus('sent')
        setMode('verification')
      } else {
        setError(getApiErrorMessage(apiError, t('auth.signInFailed')))
      }
    } finally {
      setIsLoading(false)
    }
  }

  async function handleNativeGoogleLogin() {
    setIsLoading(true)
    setError('')
    setNativeAuthFeedback(null)

    try {
      const idToken = await signInWithGoogleNative(googleClientId)
      const authData = await loginWithGoogle(idToken)
      await handleAuthSuccess(authData)
    } catch (loginError) {
      const mappedError = mapNativeAuthError(loginError)

      if (mappedError.shouldClearSession) {
        try {
          await clearSession()
        } catch {
          // clearSession clears in-memory and web state synchronously before
          // propagating secure-storage removal failures. Log classification
          // only; never include credential-bearing error objects.
          console.warn('event=native_google.failed_login_cleanup_failure')
        }
      }

      setNativeAuthFeedback(mappedError)
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
      if (authData.email_verification_required) {
        setVerificationEmail(registerForm.email.trim().toLowerCase())
        setVerificationStatus(authData.email_verification_sent ? 'sent' : 'delivery_pending')
        setMode('verification')
        setResendCooldown(60)
      } else {
        await handleAuthSuccess(authData)
      }
    } catch (apiError) {
      setError(getApiErrorMessage(apiError, t('auth.accountCreateFailed')))
    } finally {
      setIsLoading(false)
    }
  }

  async function handleResendVerification() {
    if (!verificationEmail || resendCooldown > 0 || isLoading) return
    setIsLoading(true)
    setVerificationMessage('')
    try {
      await resendVerificationEmail(verificationEmail)
      setVerificationMessage(t('auth.resendAccepted'))
      setResendCooldown(60)
    } catch (apiError) {
      const code = apiError?.response?.data?.code
      setVerificationMessage(
        code === 'VERIFICATION_COOLDOWN'
          ? t('auth.resendCooldown')
          : t('auth.accountCreateFailed'),
      )
    } finally {
      setIsLoading(false)
    }
  }

  function returnToLogin() {
    window.history.replaceState(null, '', '/')
    setMode('login')
    setVerificationStatus('idle')
    setVerificationMessage('')
  }

  if (mode === 'verification') {
    const statusMessage = {
      verifying: t('auth.verifyingEmail'),
      verified: t('auth.emailVerified'),
      already_used: t('auth.verificationAlreadyUsed'),
      expired: t('auth.verificationExpired'),
      invalid: t('auth.verificationInvalid'),
      sent: t('auth.verifyEmailSent', { email: verificationEmail }),
      delivery_pending: t('auth.verifyEmailDeliveryPending'),
    }[verificationStatus]

    return (
      <main className="login-page">
        <section className="login-panel verification-panel" aria-labelledby="verification-title">
          <h1 id="verification-title">{t('auth.verifyEmailTitle')}</h1>
          <p role={verificationStatus === 'invalid' || verificationStatus === 'expired' ? 'alert' : 'status'}>
            {statusMessage}
          </p>
          {verificationEmail && verificationStatus !== 'verified' && verificationStatus !== 'already_used' ? (
            <button
              className="auth-submit"
              disabled={isLoading || resendCooldown > 0}
              onClick={handleResendVerification}
              type="button"
            >
              {t('auth.resendVerification')}{resendCooldown > 0 ? ` (${resendCooldown})` : ''}
            </button>
          ) : null}
          {verificationMessage ? <p role="status">{verificationMessage}</p> : null}
          <button className="auth-secondary" onClick={returnToLogin} type="button">
            {t('auth.backToLogin')}
          </button>
        </section>
      </main>
    )
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
        {isNativeRuntime() ? (
          nativeGoogleStatus === 'unavailable' ? (
            <p className="google-native-unavailable">{t('auth.googleNativeUnavailable')}</p>
          ) : (
            <button
              className="google-native-button"
              disabled={isLoading || nativeGoogleStatus !== 'ready'}
              onClick={handleNativeGoogleLogin}
              type="button"
            >
              {t('auth.continueWithGoogle')}
            </button>
          )
        ) : (
          <div ref={buttonRef} className="google-login-button" />
        )}
        {nativeAuthFeedback ? (
          <p
            className={nativeAuthFeedback.severity === 'info' ? 'login-info' : 'login-error'}
            role={nativeAuthFeedback.severity === 'info' ? 'status' : 'alert'}
          >
            {t(nativeAuthFeedback.messageKey)}
          </p>
        ) : null}
        {isLoading ? <p className="login-status">{t('auth.signingIn')}</p> : null}
      </section>
    </main>
  )
}

export default LoginPage
