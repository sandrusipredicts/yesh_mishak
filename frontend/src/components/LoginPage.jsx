import { useEffect, useRef, useState } from 'react'

import { loginWithGoogle } from '../api/auth'

const GOOGLE_SCRIPT_SRC = 'https://accounts.google.com/gsi/client'

function loadGoogleScript() {
  const existingScript = document.querySelector(`script[src="${GOOGLE_SCRIPT_SRC}"]`)
  if (existingScript) {
    return Promise.resolve()
  }

  return new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.src = GOOGLE_SCRIPT_SRC
    script.async = true
    script.defer = true
    script.onload = resolve
    script.onerror = reject
    document.head.appendChild(script)
  })
}

function LoginPage({ onLogin }) {
  const buttonRef = useRef(null)
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const googleClientId = import.meta.env.VITE_GOOGLE_CLIENT_ID

  useEffect(() => {
    let isMounted = true

    async function initializeGoogleLogin() {
      if (!googleClientId) {
        setError('Google login is missing VITE_GOOGLE_CLIENT_ID.')
        return
      }

      try {
        await loadGoogleScript()

        if (!isMounted || !window.google || !buttonRef.current) {
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
              localStorage.setItem('access_token', authData.access_token)
              localStorage.setItem('currentUserId', authData.user.id)
              localStorage.setItem('currentUserName', authData.user.name)
              localStorage.setItem('currentUserEmail', authData.user.email)
              onLogin?.(authData.user)
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
  }, [googleClientId, onLogin])

  return (
    <main className="login-page">
      <section className="login-panel" aria-labelledby="login-title">
        <h1 id="login-title">yesh_mishak</h1>
        <p>Sign in to open and join games.</p>
        <div ref={buttonRef} className="google-login-button" />
        {isLoading ? <p className="login-status">Signing in...</p> : null}
        {error ? <p className="login-error">{error}</p> : null}
      </section>
    </main>
  )
}

export default LoginPage
