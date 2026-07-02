import { useCallback, useEffect, useState } from 'react'
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
import {
  clearSession,
  getToken,
  getUserMetadata,
  initSessionStorage,
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

  useEffect(() => {
    let isMounted = true

    initSessionStorage()
      .catch((storageError) => {
        console.warn('Session storage initialization failed; starting logged out.', storageError)
      })
      .finally(() => {
        if (isMounted) {
          setCurrentUser(getStoredUser())
          setIsSessionReady(true)
        }
      })

    return () => {
      isMounted = false
    }
  }, [])

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
    logoutFromServer()
    clearSession().catch((cleanupError) => {
      console.warn('Session cleanup on logout failed.', cleanupError)
    })
    setCurrentUser(null)
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
      {content}
    </>
  )

  if (!isSessionReady) {
    return null
  }

  if (!isLanguageSelected) {
    return <LanguageSelectionScreen onSelected={() => setIsLanguageSelected(true)} />
  }

  if (pathname === '/admin') {
    return renderWithOfflineBanner(
      <AdminRoute
        onForbidden={handleAdminForbidden}
        onLogin={setCurrentUser}
        onUnauthorized={handleLogout}
      >
        <AdminPage />
      </AdminRoute>,
    )
  }

  if (!currentUser) {
    return renderWithOfflineBanner(<LoginPage onLogin={setCurrentUser} />)
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
