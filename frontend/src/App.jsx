import { useCallback, useEffect, useRef, useState } from 'react'
import { App as CapacitorApp } from '@capacitor/app'
import { useTranslation } from 'react-i18next'

import './App.css'
import AdminRoute from './components/AdminRoute'
import LanguageSelectionScreen from './components/LanguageSelectionScreen'
import LoginPage from './components/LoginPage'
import OfflineBanner from './components/OfflineBanner'
import AdminPage from './pages/AdminPage'
import MapPage from './pages/MapPage'
import MyGamesPage from './pages/MyGamesPage'
import OnboardingPage from './pages/OnboardingPage'
import { getStoredSessionUserId, logoutFromServer } from './api/auth'
import { getMyGames } from './api/games'
import {
  clearSession,
  getToken,
  getUserMetadata,
  initSessionStorage,
  isNativeRuntime,
} from './api/sessionStorage'
import { startForegroundPushNotifications } from './firebaseMessaging'
import { hasSelectedLanguage } from './i18n'

function getStoredUser() {
  const accessToken = getToken()
  const id = getStoredSessionUserId()

  if (!accessToken || !id) {
    return null
  }

  const metadata = getUserMetadata()

  return {
    id,
    name: metadata.name,
    email: metadata.email,
    username: metadata.username,
  }
}

function App() {
  const { t } = useTranslation()
  const [pathname, setPathname] = useState(() => window.location.pathname)
  const [isSessionReady, setIsSessionReady] = useState(false)
  const [currentUser, setCurrentUser] = useState(null)
  const [isOnboardingDone, setIsOnboardingDone] = useState(
    () => localStorage.getItem('onboarding_done') === 'true',
  )
  const [isLanguageSelected, setIsLanguageSelected] = useState(hasSelectedLanguage)
  const [logoutWarning, setLogoutWarning] = useState('')
  const validationPromiseRef = useRef(null)
  const sessionEpochRef = useRef(0)

  const validateStoredSession = useCallback(async () => {
    if (validationPromiseRef.current) {
      return validationPromiseRef.current
    }

    // Logout bumps the epoch; any validation started before it must not
    // touch auth state when it settles, even if /games/me succeeds late.
    const epoch = sessionEpochRef.current

    const validationPromise = (async () => {
      const storedUser = getStoredUser()

      if (!storedUser) {
        if (getToken()) {
          await clearSession().catch((cleanupError) => {
            console.warn('Session cleanup failed.', cleanupError)
          })
        }
        setCurrentUser(null)
        return null
      }

      try {
        await getMyGames()

        if (sessionEpochRef.current !== epoch || !getToken()) {
          return null
        }

        setCurrentUser(storedUser)
        return storedUser
      } catch {
        if (sessionEpochRef.current !== epoch) {
          return null
        }

        await clearSession().catch((cleanupError) => {
          console.warn('Session cleanup failed.', cleanupError)
        })
        setCurrentUser(null)
        return null
      }
    })()

    validationPromiseRef.current = validationPromise

    try {
      return await validationPromise
    } finally {
      if (validationPromiseRef.current === validationPromise) {
        validationPromiseRef.current = null
      }
    }
  }, [])

  useEffect(() => {
    let isMounted = true

    initSessionStorage()
      .then(() => {
        if (isNativeRuntime()) {
          return validateStoredSession()
        }

        setCurrentUser(getStoredUser())
        return null
      })
      .catch(async (storageError) => {
        console.warn('Session storage initialization failed; starting logged out.', storageError)
        await clearSession().catch((cleanupError) => {
          console.warn('Session cleanup failed.', cleanupError)
        })
        setCurrentUser(null)
      })
      .finally(() => {
        if (isMounted) {
          setIsSessionReady(true)
        }
      })

    return () => {
      isMounted = false
    }
  }, [validateStoredSession])

  useEffect(() => {
    function handleVisibilityChange() {
      if (document.visibilityState === 'visible' && isNativeRuntime() && getToken()) {
        validateStoredSession()
      }
    }

    document.addEventListener('visibilitychange', handleVisibilityChange)

    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange)
    }
  }, [validateStoredSession])

  useEffect(() => {
    if (!isNativeRuntime()) {
      return undefined
    }

    let listenerHandle = null
    let isDisposed = false

    CapacitorApp.addListener('appStateChange', ({ isActive }) => {
      if (isActive && getToken()) {
        validateStoredSession()
      }
    }).then((handle) => {
      if (isDisposed) {
        handle.remove()
      } else {
        listenerHandle = handle
      }
    })

    return () => {
      isDisposed = true
      listenerHandle?.remove()
    }
  }, [validateStoredSession])

  useEffect(() => {
    function handlePopState() {
      setPathname(window.location.pathname)
    }

    window.addEventListener('popstate', handlePopState)

    return () => {
      window.removeEventListener('popstate', handlePopState)
    }
  }, [])

  useEffect(() => {
    function refreshStoredUser() {
      setCurrentUser(getStoredUser())
    }

    window.addEventListener('storage', refreshStoredUser)
    window.addEventListener('auth-session-changed', refreshStoredUser)

    return () => {
      window.removeEventListener('storage', refreshStoredUser)
      window.removeEventListener('auth-session-changed', refreshStoredUser)
    }
  }, [])

  useEffect(() => {
    if (!currentUser) {
      return
    }

    startForegroundPushNotifications().catch((pushError) => {
      console.warn('Foreground push notification setup failed.', pushError)
    })
  }, [currentUser])

  const handleLogout = useCallback(() => {
    // Invalidate any in-flight or deduplicated session validation before
    // clearing storage so a late /games/me success cannot restore the user.
    sessionEpochRef.current += 1
    validationPromiseRef.current = null

    logoutFromServer()
    setCurrentUser(null)
    setLogoutWarning('')
    clearSession().catch((cleanupError) => {
      console.warn('Session cleanup on logout failed.', cleanupError)
      setLogoutWarning(t('auth.logoutCleanupError'))
    })
  }, [t])

  const handleLogin = useCallback((user) => {
    setLogoutWarning('')
    setCurrentUser(user)
  }, [])

  const handleOnboardingComplete = useCallback(() => {
    setIsOnboardingDone(true)
  }, [])

  const handleAdminForbidden = useCallback(() => {
    window.history.replaceState(null, '', '/')
    setPathname('/')
  }, [])

  const renderWithOfflineBanner = (content) => (
    <>
      <OfflineBanner />
      {logoutWarning ? (
        <div className="logout-warning" role="alert">
          {logoutWarning}
        </div>
      ) : null}
      {content}
    </>
  )

  if (!isSessionReady) {
    return (
      <main className="auth-checking" data-testid="auth-checking" aria-busy="true">
        <p>{t('auth.checkingSession')}</p>
      </main>
    )
  }

  if (!isLanguageSelected) {
    return <LanguageSelectionScreen onSelected={() => setIsLanguageSelected(true)} />
  }

  if (pathname === '/admin') {
    return renderWithOfflineBanner(
      <AdminRoute
        onForbidden={handleAdminForbidden}
        onLogin={handleLogin}
        onUnauthorized={handleLogout}
      >
        <AdminPage />
      </AdminRoute>,
    )
  }

  if (!currentUser) {
    return renderWithOfflineBanner(<LoginPage onLogin={handleLogin} />)
  }

  if (!isOnboardingDone) {
    return renderWithOfflineBanner(<OnboardingPage onComplete={handleOnboardingComplete} />)
  }

  const navigateTo = (path) => {
    window.history.pushState(null, '', path)
    setPathname(path)
  }

  if (pathname === '/my-games') {
    return renderWithOfflineBanner(<MyGamesPage onBack={() => navigateTo('/')} />)
  }

  return renderWithOfflineBanner(
    <>
      <MapPage currentUserId={currentUser.id} />
      <div className="auth-toolbar">
        <span>{currentUser.name || currentUser.email}</span>
        <button type="button" onClick={() => navigateTo('/my-games')}>
          {t('myGames.title')}
        </button>
        <button type="button" onClick={handleLogout}>
          {t('app.logout')}
        </button>
      </div>
    </>,
  )
}

export default App
