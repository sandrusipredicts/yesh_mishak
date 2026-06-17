import { useCallback, useEffect, useRef, useState } from 'react'

import {
  loginWithGoogle,
  loginWithPassword,
  registerWithPassword,
  saveAuthSession,
} from '../api/auth'

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
  const buttonRef = useRef(null)
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
  const googleClientId = import.meta.env.VITE_GOOGLE_CLIENT_ID

  const handleAuthSuccess = useCallback((authData) => {
    const sessionUser = saveAuthSession(authData)
    onLogin?.(sessionUser)
  }, [onLogin])

  useEffect(() => {
    let isMounted = true

    async function initializeGoogleLogin() {
      if (!googleClientId) {
        setError('Google login is missing VITE_GOOGLE_CLIENT_ID.')
        return
      }

      try {
        await loadGoogleScript()

        if (!isMounted) {
          return
        }

        if (!window.google?.accounts?.id) {
          setError('Google login loaded but is not ready yet.')
          return
        }

        if (!buttonRef.current) {
          setError('Google login button could not be mounted.')
          return
        }

        window.google.accounts.id.initialize({
          client_id: googleClientId,
          callback: async (response) => {
            if (!response.credential) {
              setError('Google did not return a credential.')
              return
            }

            setIsLoading(true)
            setError('')

            try {
              const authData = await loginWithGoogle(response.credential)
              handleAuthSuccess(authData)
            } catch {
              setError('Could not sign in with Google. Please try again.')
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
            setError('Google login button could not be rendered.')
          }
        }, 0)
      } catch {
        if (isMounted) {
          setError('Could not load Google login.')
        }
      }
    }

    initializeGoogleLogin()

    return () => {
      isMounted = false
    }
  }, [googleClientId, handleAuthSuccess])

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

  async function handlePasswordLogin(event) {
    event.preventDefault()
    setIsLoading(true)
    setError('')

    try {
      const authData = await loginWithPassword(loginForm)
      handleAuthSuccess(authData)
    } catch (apiError) {
      setError(getApiErrorMessage(apiError, 'Could not sign in. Please check your details.'))
    } finally {
      setIsLoading(false)
    }
  }

  async function handleRegister(event) {
    event.preventDefault()
    setIsLoading(true)
    setError('')

    try {
      const authData = await registerWithPassword(registerForm)
      handleAuthSuccess(authData)
    } catch (apiError) {
      setError(getApiErrorMessage(apiError, 'Could not create your account.'))
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <main className="login-page">
      <section className="login-panel" aria-labelledby="login-title">
        <h1 id="login-title">yesh_mishak</h1>
        <p>Sign in to open and join games.</p>

        <div className="auth-mode-tabs" role="tablist" aria-label="Authentication method">
          <button
            type="button"
            className={mode === 'login' ? 'active' : ''}
            onClick={() => {
              setMode('login')
              setError('')
            }}
          >
            Login
          </button>
          <button
            type="button"
            className={mode === 'register' ? 'active' : ''}
            onClick={() => {
              setMode('register')
              setError('')
            }}
          >
            Register
          </button>
        </div>

        {mode === 'login' ? (
          <form className="auth-form" onSubmit={handlePasswordLogin}>
            <label>
              <span>Username</span>
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
              <span>Password</span>
              <input
                autoComplete="current-password"
                name="password"
                onChange={updateLoginForm}
                required
                type="password"
                value={loginForm.password}
              />
            </label>
            <button className="auth-submit" disabled={isLoading} type="submit">
              Sign in
            </button>
          </form>
        ) : (
          <form className="auth-form" onSubmit={handleRegister}>
            <label>
              <span>Full name</span>
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
              <span>Username</span>
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
              <span>Email</span>
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
              <span>Phone number</span>
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
              <span>Password</span>
              <input
                autoComplete="new-password"
                minLength={8}
                name="password"
                onChange={updateRegisterForm}
                required
                type="password"
                value={registerForm.password}
              />
            </label>
            <label>
              <span>Confirm password</span>
              <input
                autoComplete="new-password"
                minLength={8}
                name="password_confirm"
                onChange={updateRegisterForm}
                required
                type="password"
                value={registerForm.password_confirm}
              />
            </label>
            <button className="auth-submit" disabled={isLoading} type="submit">
              Create account
            </button>
          </form>
        )}

        <div className="auth-divider" aria-hidden="true">
          <span />
          <strong>or</strong>
          <span />
        </div>
        <div ref={buttonRef} className="google-login-button" />
        {isLoading ? <p className="login-status">Signing in...</p> : null}
        {error ? <p className="login-error">{error}</p> : null}
      </section>
    </main>
  )
}

export default LoginPage
