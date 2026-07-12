import { useCallback, useEffect, useRef, useState } from 'react'
import { App as CapacitorApp } from '@capacitor/app'
import { useTranslation } from 'react-i18next'

import './App.css'
import AdminRoute from './components/AdminRoute'
import ForgotPasswordPage from './components/ForgotPasswordPage'
import LanguageSelectionScreen from './components/LanguageSelectionScreen'
import LoginPage from './components/LoginPage'
import OfflineBanner from './components/OfflineBanner'
import ResetPasswordPage from './components/ResetPasswordPage'
import AdminPage from './pages/AdminPage'
import MapPage from './pages/MapPage'
import MyGamesPage from './pages/MyGamesPage'
import OnboardingPage from './pages/OnboardingPage'
import { getStoredSessionUserId, logoutFromServer } from './api/auth'
import { isNativeGoogleSupported, signOutGoogleNative } from './api/nativeGoogleAuth'
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
import { CANONICAL_APP_LINK_HOST, normalizeAppLinkUrl, parseAppPathname } from './utils/appLinkRoutes'

// Shared by every deep-linkable resource type (currently 'game' and
// 'field') so App.jsx has exactly one pending-link storage/hand-off
// mechanism instead of one per resource type (ISSUE-272, extended for
// ISSUE-273). Target shape: { routeType: 'game' | 'field', resourceId, action }.
const PENDING_DEEP_LINK_STORAGE_KEY = 'pending_deep_link'

function readPendingDeepLink() {
  if (typeof sessionStorage === 'undefined') {
    return null
  }

  try {
    const stored = JSON.parse(sessionStorage.getItem(PENDING_DEEP_LINK_STORAGE_KEY) ?? 'null')
    return stored && typeof stored.routeType === 'string' && typeof stored.resourceId === 'string'
      ? stored
      : null
  } catch {
    return null
  }
}

function writePendingDeepLink(target) {
  if (typeof sessionStorage === 'undefined') {
    return
  }

  if (target) {
    sessionStorage.setItem(PENDING_DEEP_LINK_STORAGE_KEY, JSON.stringify(target))
  } else {
    sessionStorage.removeItem(PENDING_DEEP_LINK_STORAGE_KEY)
  }
}

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
  const [loginNotice, setLoginNotice] = useState(
    () => new URLSearchParams(window.location.search).get('reset') === 'success'
      ? t('auth.passwordResetSuccess')
      : '',
  )
  const [persistenceWarning, setPersistenceWarning] = useState('')
  const [deepLinkTarget, setDeepLinkTarget] = useState(() => readPendingDeepLink())
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

  const navigateTo = useCallback((path, { replace = false } = {}) => {
    const nextUrl = new URL(path, window.location.origin)

    if (window.location.pathname === nextUrl.pathname && window.location.search === nextUrl.search) {
      setPathname(nextUrl.pathname)
      return
    }

    if (replace) {
      window.history.replaceState(null, '', `${nextUrl.pathname}${nextUrl.search}`)
    } else {
      window.history.pushState(null, '', `${nextUrl.pathname}${nextUrl.search}`)
    }
    setPathname(nextUrl.pathname)
  }, [])

  // Central hand-off point for a resolved deep link (game or field),
  // regardless of whether it arrived via an external URL (appUrlOpen /
  // launch URL / canonical-host page load) or an in-app pathname change.
  // Persisted to sessionStorage so the target survives a login redirect or
  // page reload; MapPage clears it once resolved (see handleDeepLinkHandled).
  const applyDeepLinkTarget = useCallback((target) => {
    setDeepLinkTarget(target)
    writePendingDeepLink(target)
  }, [])

  const handleDeepLinkHandled = useCallback(() => {
    setDeepLinkTarget(null)
    writePendingDeepLink(null)
  }, [])

  const handleIncomingAppLink = useCallback((url, { replace = false } = {}) => {
    const normalized = normalizeAppLinkUrl(url)

    if (!normalized.ok) {
      console.warn('Rejected app link URL.', normalized.reason)
      return
    }

    // Game (ISSUE-272) and field (ISSUE-273) detail resolution both flow
    // through applyDeepLinkTarget + MapPage; this layer only validates the
    // external URL and hands off to the existing app routes.
    if ((normalized.routeType === 'game' || normalized.routeType === 'field') && normalized.resourceId) {
      applyDeepLinkTarget({
        routeType: normalized.routeType,
        resourceId: normalized.resourceId,
        action: normalized.action || '',
      })
    }

    navigateTo(normalized.navigationPath, { replace })
  }, [applyDeepLinkTarget, navigateTo])

  useEffect(() => {
    if (window.location.hostname === CANONICAL_APP_LINK_HOST && window.location.pathname !== '/reset-password') {
      const timeoutId = window.setTimeout(() => {
        handleIncomingAppLink(window.location.href, { replace: true })
      }, 0)

      return () => {
        window.clearTimeout(timeoutId)
      }
    }

    return undefined
  }, [handleIncomingAppLink])

  // Same-origin counterpart: resolves a direct/bookmarked/back-forward
  // navigation to /game/{id} or /field/{id} regardless of hostname (covers
  // local dev, staging, and any host that isn't the canonical App Links
  // domain, which the effect above intentionally ignores). Host validation
  // is irrelevant here since window.location.pathname is same-origin by
  // construction.
  useEffect(() => {
    function resolvePathnameDeepLink() {
      const resolved = parseAppPathname(pathname, window.location.search)

      if (
        resolved.ok &&
        (resolved.routeType === 'game' || resolved.routeType === 'field') &&
        resolved.resourceId
      ) {
        applyDeepLinkTarget({
          routeType: resolved.routeType,
          resourceId: resolved.resourceId,
          action: resolved.action || '',
        })

        if (window.location.pathname !== '/') {
          navigateTo('/', { replace: true })
        }
      }
    }

    const timeoutId = window.setTimeout(resolvePathnameDeepLink, 0)

    return () => {
      window.clearTimeout(timeoutId)
    }
  }, [pathname, applyDeepLinkTarget, navigateTo])

  useEffect(() => {
    if (!isNativeRuntime()) {
      return undefined
    }

    let listenerHandle = null
    let isDisposed = false

    CapacitorApp.getLaunchUrl()
      .then((launchUrl) => {
        if (!isDisposed && launchUrl?.url) {
          handleIncomingAppLink(launchUrl.url, { replace: true })
        }
      })
      .catch((launchUrlError) => {
        console.warn('Unable to read Capacitor launch URL.', launchUrlError)
      })

    CapacitorApp.addListener('appUrlOpen', (event) => {
      if (event?.url) {
        handleIncomingAppLink(event.url)
      }
    }).then((handle) => {
      if (isDisposed) {
        handle.remove()
      } else {
        listenerHandle = handle
      }
    }).catch((listenerError) => {
      console.warn('Unable to register app link listener.', listenerError)
    })

    return () => {
      isDisposed = true
      listenerHandle?.remove()
    }
  }, [handleIncomingAppLink])

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
    function handlePersistenceChanged(event) {
      setPersistenceWarning(
        event.detail?.persisted ? '' : t('auth.persistenceWarning'),
      )
    }

    window.addEventListener('auth-persistence-changed', handlePersistenceChanged)

    return () => {
      window.removeEventListener('auth-persistence-changed', handlePersistenceChanged)
    }
  }, [t])

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

    if (isNativeGoogleSupported()) {
      // Best-effort provider sign-out so the next Google login shows the
      // account picker; never affects app logout (handled inside).
      signOutGoogleNative()
    }

    setCurrentUser(null)
    setLogoutWarning('')
    setPersistenceWarning('')
    handleDeepLinkHandled()
    clearSession().catch((cleanupError) => {
      console.warn('Session cleanup on logout failed.', cleanupError)
      setLogoutWarning(t('auth.logoutCleanupError'))
    })
  }, [handleDeepLinkHandled, t])

  const handleLogin = useCallback((user) => {
    setLogoutWarning('')
    setLoginNotice('')
    setCurrentUser(user)
  }, [])

  const handlePasswordResetDone = useCallback((message) => {
    sessionEpochRef.current += 1
    validationPromiseRef.current = null
    setCurrentUser(null)
    setLogoutWarning('')
    setPersistenceWarning('')
    setLoginNotice(message)
    handleDeepLinkHandled()
    setPathname(window.location.pathname)
  }, [handleDeepLinkHandled])

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
      {persistenceWarning ? (
        <div className="persistence-warning" role="alert">
          {persistenceWarning}
        </div>
      ) : null}
      {content}
    </>
  )

  if (!isSessionReady) {
    if (pathname === '/reset-password') {
      return renderWithOfflineBanner(<ResetPasswordPage onDone={handlePasswordResetDone} />)
    }

    return (
      <main className="auth-checking" data-testid="auth-checking" aria-busy="true">
        <p>{t('auth.checkingSession')}</p>
      </main>
    )
  }

  if (!isLanguageSelected) {
    if (pathname === '/reset-password') {
      return renderWithOfflineBanner(<ResetPasswordPage onDone={handlePasswordResetDone} />)
    }

    return <LanguageSelectionScreen onSelected={() => setIsLanguageSelected(true)} />
  }

  if (pathname === '/reset-password') {
    return renderWithOfflineBanner(<ResetPasswordPage onDone={handlePasswordResetDone} />)
  }

  if (pathname === '/forgot-password') {
    return renderWithOfflineBanner(
      <ForgotPasswordPage onBackToLogin={() => navigateTo('/login')} />,
    )
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
    return renderWithOfflineBanner(
      <LoginPage
        notice={loginNotice}
        onForgotPassword={() => navigateTo('/forgot-password')}
        onLogin={handleLogin}
      />,
    )
  }

  if (!isOnboardingDone) {
    return renderWithOfflineBanner(<OnboardingPage onComplete={handleOnboardingComplete} />)
  }

  if (pathname === '/my-games') {
    return renderWithOfflineBanner(<MyGamesPage onBack={() => navigateTo('/')} />)
  }

  return renderWithOfflineBanner(
    <>
      <MapPage
        currentUserId={currentUser.id}
        deepLinkTarget={deepLinkTarget}
        onDeepLinkHandled={handleDeepLinkHandled}
      />
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
