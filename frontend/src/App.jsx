import { useCallback, useEffect, useRef, useState } from 'react'
import { App as CapacitorApp } from '@capacitor/app'
import { Capacitor } from '@capacitor/core'
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
import MyReportsPage from './pages/MyReportsPage'
import OnboardingPage from './pages/OnboardingPage'
import SettingsPage from './pages/SettingsPage'
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
import { requestFirebasePushToken, startForegroundPushNotifications } from './firebaseMessaging'
import {
  getCurrentToken,
  initNativePush,
  isNativePushSupported,
  teardownNativePush,
} from './api/nativePushNotifications'
import { deletePushToken, savePushToken } from './api/notifications'
import { recordLinkOpen } from './api/shareAnalytics'
import { hasSelectedLanguage } from './i18n'
import {
  addBreadcrumb,
  captureMessage,
  clearUser as clearMonitoringUser,
  setUser as setMonitoringUser,
} from './monitoring/index.js'
import { CANONICAL_APP_LINK_HOST, normalizeAppLinkUrl, parseAppPathname } from './utils/appLinkRoutes'
import { getOrCreateInstallationId } from './utils/installationId'
import { createPushTokenSync } from './utils/pushTokenSync'
import {
  resolveAccountCity,
  resolveOnboardingState,
  saveOnboardingState,
} from './onboarding/onboardingStorage'
import AccountCityStep from './components/onboarding/AccountCityStep'

// Shared by every deep-linkable resource type (currently 'game' and
// 'field') so App.jsx has exactly one pending-link storage/hand-off
// mechanism instead of one per resource type (ISSUE-272, extended for
// ISSUE-273). Target shape: { routeType: 'game' | 'field', resourceId, action }.
const PENDING_DEEP_LINK_STORAGE_KEY = 'pending_deep_link'

function buildDeepLinkTarget(resolved, { deferredForAuth = false } = {}) {
  return {
    routeType: resolved.routeType,
    resourceId: resolved.resourceId,
    action: resolved.action || '',
    analyticsDeferred: deferredForAuth,
  }
}

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

function isNetworkValidationFailure(error) {
  return !error?.response
}

function App() {
  const { t } = useTranslation()
  const [pathname, setPathname] = useState(() => window.location.pathname)
  const [isSessionReady, setIsSessionReady] = useState(false)
  const [currentUser, setCurrentUser] = useState(null)
  const [onboardingState, setOnboardingState] = useState(
    () => resolveOnboardingState().state,
  )
  // Tracks which userId the resolved city below actually belongs to, so a
  // stale value from a just-logged-out account can never leak into a
  // render for a newly-logged-in one (E08-02 follow-up fix): resolution is
  // async (deferred a tick), but `currentUser` can change synchronously in
  // the same tick, so `resolvedAccountCity` is *derived* — comparing
  // `cityResolution.forUserId` against the live `currentUser.id` — rather
  // than trusted as its own always-current piece of state.
  const [cityResolution, setCityResolution] = useState({ forUserId: null, city: undefined })
  const resolvedAccountCity = currentUser && cityResolution.forUserId === currentUser.id
    ? cityResolution.city
    : undefined
  const [mapEntryIntent, setMapEntryIntent] = useState(null)
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
  const pushTokenSyncRef = useRef(null)

  function getPushTokenSync() {
    if (!pushTokenSyncRef.current) {
      pushTokenSyncRef.current = createPushTokenSync({
        save: (token, options) => savePushToken(token, options),
        onSyncFailed: (error) => {
          console.warn('[E04-05 PUSH DEBUG] token sync exhausted retries',
            error?.response?.status || error?.message || error)
        },
      })
    }
    return pushTokenSyncRef.current
  }

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
      } catch (validationError) {
        if (sessionEpochRef.current !== epoch) {
          return null
        }

        if (isNativeRuntime() && isNetworkValidationFailure(validationError)) {
          setCurrentUser(storedUser)
          return storedUser
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

    function handleOnline() {
      if (isNativeRuntime() && getToken()) {
        validateStoredSession()
      }
    }

    document.addEventListener('visibilitychange', handleVisibilityChange)
    window.addEventListener('online', handleOnline)

    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange)
      window.removeEventListener('online', handleOnline)
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
        pushTokenSyncRef.current?.retryPending()
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
      // Category only -- never the raw url, which may carry query params.
      addBreadcrumb({ category: 'deep_link', message: 'deep link resolution', level: 'warning', data: { category: 'rejected', reason: normalized.reason } })
      return
    }

    // Game (ISSUE-272) and field (ISSUE-273) detail resolution both flow
    // through applyDeepLinkTarget + MapPage; this layer only validates the
    // external URL and hands off to the existing app routes.
    if ((normalized.routeType === 'game' || normalized.routeType === 'field') && normalized.resourceId) {
      const deferredForAuth = !getToken()
      if (deferredForAuth) {
        recordLinkOpen(normalized, 'deferred_for_auth')
      }
      applyDeepLinkTarget(buildDeepLinkTarget(normalized, { deferredForAuth }))
      addBreadcrumb({ category: 'deep_link', message: 'deep link resolution', level: 'info', data: { category: normalized.routeType, deferredForAuth } })
    } else if (normalized.routeType === 'fallback') {
      recordLinkOpen(normalized, 'invalid')
      addBreadcrumb({ category: 'deep_link', message: 'deep link resolution', level: 'warning', data: { category: 'invalid' } })
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
        const deferredForAuth = !getToken()
        if (deferredForAuth) {
          recordLinkOpen(resolved, 'deferred_for_auth')
        }
        applyDeepLinkTarget(buildDeepLinkTarget(resolved, { deferredForAuth }))

        if (window.location.pathname !== '/') {
          navigateTo('/', { replace: true })
        }
      } else if (resolved.ok && resolved.routeType === 'fallback') {
        recordLinkOpen(resolved, 'invalid')
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

  // Monitoring user-context lifecycle: this single effect is the only place
  // Sentry.setUser/clearUser is ever called, so every path that changes
  // currentUser (login, logout, session restore, account switch) stays in
  // sync automatically instead of needing a call at each call site.
  // setUser() itself always clears before setting (see monitoring/client.js),
  // so an account switch (A -> B) can never leak A's context into B's events.
  useEffect(() => {
    if (currentUser?.id) {
      setMonitoringUser(currentUser.id)
      addBreadcrumb({ category: 'auth', message: 'authentication state changed', level: 'info', data: { state: 'authenticated' } })
    } else {
      clearMonitoringUser()
      addBreadcrumb({ category: 'auth', message: 'authentication state changed', level: 'info', data: { state: 'anonymous' } })
    }
  }, [currentUser?.id])

  useEffect(() => {
    if (isSessionReady) {
      addBreadcrumb({ category: 'app', message: 'application startup completed', level: 'info' })
    }
  }, [isSessionReady])

  // E08-02 follow-up fix: onboarding completion/permission-education flags
  // are device-scoped by design (a second account must not repeat the
  // walkthrough or be re-prompted for permissions Android already knows
  // about), but the starting city is personal data. Re-resolve it for
  // *this* account on every login/session-restore, reading storage fresh
  // rather than from React state. Every route below that is specific to an
  // authenticated account (map, settings, my-games, my-reports) is gated
  // behind `resolvedAccountCity !== undefined`, so — unlike a plain
  // "correct it after the fact" effect — nothing can mount and consume a
  // stale or another account's city while this resolution is in flight.
  useEffect(() => {
    if (!currentUser) {
      return undefined
    }

    // Deferred a tick (matching the deep-link effects above) so setState
    // isn't called synchronously within the effect body itself. Safe to
    // defer: the render gate below means nothing consumes the old value
    // in the meantime.
    const timeoutId = window.setTimeout(() => {
      const freshState = resolveOnboardingState().state
      const resolvedCity = resolveAccountCity(currentUser.id, freshState)

      if (freshState.city !== resolvedCity) {
        const corrected = saveOnboardingState({ ...freshState, city: resolvedCity })
        if (corrected.ok) {
          setOnboardingState(corrected.state)
        }
      }

      setCityResolution({ forUserId: currentUser.id, city: resolvedCity })
      setMapEntryIntent(resolvedCity ? { type: 'city', city: resolvedCity } : null)
    }, 0)

    return () => {
      window.clearTimeout(timeoutId)
    }
  }, [currentUser])

  // Called once the current account (which had no city of its own) picks
  // one via the city-only requiredStep flow (AccountCityStep). The city is
  // already persisted to the account-scoped store by AccountCityStep
  // itself; this just unblocks the render gate immediately with the fresh
  // value instead of waiting for the next currentUser-keyed resolution.
  const handleAccountCitySelected = useCallback((city) => {
    if (!currentUser) {
      return
    }
    setCityResolution({ forUserId: currentUser.id, city })
    setMapEntryIntent({ type: 'city', city })
  }, [currentUser])

  async function handleEnableNotifications() {
    addBreadcrumb({ category: 'push', message: 'permission request started', level: 'info', data: { category: 'push_registration' } })
    if (isNativePushSupported()) {
      const result = await initNativePush({
      onTokenReceived: (token) => {
        console.info('[E04-01 PUSH DEBUG] token upload started, token length:', token.length)
        getPushTokenSync().sync(token, {
          platform: Capacitor.getPlatform(),
          installationId: getOrCreateInstallationId(),
        })
      },
      onTokenError: (error) => {
        console.warn('[E04-01 PUSH DEBUG] registration error:', error?.message || error)
        // Permission was already granted by this point (see outcome mapping
        // below) -- a token-delivery failure here is unexpected, not a
        // normal denial, so it is reportable.
        addBreadcrumb({ category: 'push', message: 'push registration failed unexpectedly', level: 'warning' })
        captureMessage('Native push token registration failed after permission was granted', 'warning')
      },
      onForegroundNotification: () => {
        window.dispatchEvent(new CustomEvent('native-push-received'))
      },
      onNotificationTapped: (target) => {
        if (target) {
          applyDeepLinkTarget(target)
        }
      },
      })
      console.info('[E04-01 PUSH DEBUG] explicit init result:', result?.outcome)
      // 'registration-failed' means the OS permission was already granted —
      // requestPushPermission() inside initNativePush() only reaches
      // register() after a granted check — and only the native FCM/APNs
      // handshake itself failed. That is a token-delivery problem, not a
      // permission denial: report it as 'granted' so onboarding/UI never
      // shows "notifications were not allowed" for a permission the user
      // did allow. Delivery keeps retrying through the existing
      // registration/registrationError listeners and createPushTokenSync
      // (E08-02; previously this path was mis-reported as 'denied').
      if (['registered', 'already-initialized', 'registration-failed'].includes(result?.outcome)) {
        return { outcome: 'granted' }
      }
      if (result?.outcome === 'unsupported') return { outcome: 'unsupported' }
      return { outcome: 'denied' }
    }

    try {
      const token = await requestFirebasePushToken()
      await savePushToken(token, { installationId: getOrCreateInstallationId() })
      return { outcome: 'granted' }
    } catch (error) {
      if (typeof Notification === 'undefined') return { outcome: 'unsupported' }
      console.warn('Explicit web notification enable failed.', error?.message || error)
      return { outcome: 'denied' }
    }
  }

  const handleLogout = useCallback(() => {
    // Snapshot the session token before anything below clears it. clearSession()
    // (called later in this function) nulls the in-memory token synchronously,
    // before axios's request interceptor — a deferred microtask — ever reads it
    // for the push-token unregister call, so that call needs its own pinned
    // Authorization header instead of relying on the interceptor.
    const logoutAuthToken = getToken()

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

    // Stop any in-flight/backoff-scheduled token sync before tearing down so
    // a pending retry can't upload a token for the user who just logged out.
    pushTokenSyncRef.current?.dispose()
    pushTokenSyncRef.current = null

    const pushToken = getCurrentToken()
    if (pushToken) {
      console.info('[E04-01 PUSH DEBUG] logout: deleting push token')
      deletePushToken(pushToken, { authToken: logoutAuthToken }).catch((deleteError) => {
        console.warn('[E04-01 PUSH DEBUG] logout: token delete failed', deleteError)
        // The row is not orphaned indefinitely: the next login/account switch
        // re-registers this installation's token, and the backend reassigns
        // ownership by token identity regardless of whether this delete
        // ever landed (backend/app/routers/notifications.py:save_push_token).
      })
    }
    teardownNativePush()

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

  const handleOnboardingComplete = useCallback((intent, completedState) => {
    setOnboardingState(completedState)
    setMapEntryIntent(intent)
    // The wizard's own city step already saved this account's city to the
    // account-scoped store (OnboardingPage calls setAccountCity directly);
    // sync the resolution gate immediately with the same value instead of
    // leaving it unresolved until the next currentUser-keyed effect run,
    // which wouldn't otherwise fire again since currentUser hasn't changed.
    if (currentUser) {
      setCityResolution({ forUserId: currentUser.id, city: completedState.city })
    }
  }, [currentUser])

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

  if (onboardingState.status !== 'completed') {
    return renderWithOfflineBanner(
      <OnboardingPage
        initialState={onboardingState}
        onComplete={handleOnboardingComplete}
        onEnableNotifications={handleEnableNotifications}
        userId={currentUser.id}
      />,
    )
  }

  // Device-level onboarding is complete, but this specific account's own
  // city has not been resolved yet — brief, no perceptible loading state
  // needed in practice (a synchronous localStorage read deferred one
  // tick), but nothing account-specific may render until it settles.
  if (resolvedAccountCity === undefined) {
    return null
  }

  // requiredStep = city: device onboarding never repeats (no welcome,
  // location, or notification priming replay, no native permission APIs),
  // but this account has no city of its own — ask for only that, and
  // block every other authenticated route until it's chosen.
  if (resolvedAccountCity === '') {
    return renderWithOfflineBanner(
      <AccountCityStep userId={currentUser.id} onSelected={handleAccountCitySelected} />,
    )
  }

  if (pathname === '/my-games') {
    return renderWithOfflineBanner(<MyGamesPage onBack={() => navigateTo('/')} />)
  }

  if (pathname === '/my-reports') {
    return renderWithOfflineBanner(<MyReportsPage onBack={() => navigateTo('/')} />)
  }

  if (pathname === '/settings') {
    return renderWithOfflineBanner(<SettingsPage onBack={() => navigateTo('/')} userId={currentUser.id} />)
  }

  return renderWithOfflineBanner(
    <>
      <MapPage
        currentUserId={currentUser.id}
        deepLinkTarget={deepLinkTarget}
        initialEntryIntent={mapEntryIntent}
        onEnableNotifications={handleEnableNotifications}
        onDeepLinkHandled={handleDeepLinkHandled}
      />
      <div className="auth-toolbar">
        <span>{currentUser.name || currentUser.email}</span>
        <button type="button" onClick={() => navigateTo('/my-games')}>
          {t('myGames.title')}
        </button>
        <button type="button" onClick={() => navigateTo('/my-reports')}>
          {t('myReports.title')}
        </button>
        <button type="button" onClick={() => navigateTo('/settings')}>
          {t('accountLinking.navTitle')}
        </button>
        <button type="button" onClick={handleLogout}>
          {t('app.logout')}
        </button>
      </div>
    </>,
  )
}

export default App
