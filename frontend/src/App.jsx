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
import { getStoredSessionUserId } from './api/auth'
import { startForegroundPushNotifications } from './firebaseMessaging'
import { hasSelectedLanguage } from './i18n'

function getStoredUser() {
  const accessToken = localStorage.getItem('access_token')
  const id = getStoredSessionUserId()

  if (!accessToken || !id) {
    return null
  }

  return {
    id,
    name: localStorage.getItem('currentUserName') || '',
    email: localStorage.getItem('currentUserEmail') || '',
    username: localStorage.getItem('currentUsername') || '',
  }
}

function App() {
  const { t } = useTranslation()
  const [pathname, setPathname] = useState(() => window.location.pathname)
  const [currentUser, setCurrentUser] = useState(getStoredUser)
  const [isOnboardingDone, setIsOnboardingDone] = useState(
    () => localStorage.getItem('onboarding_done') === 'true',
  )
  const [isLanguageSelected, setIsLanguageSelected] = useState(hasSelectedLanguage)

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
    localStorage.removeItem('access_token')
    localStorage.removeItem('currentUserId')
    localStorage.removeItem('currentUserName')
    localStorage.removeItem('currentUserEmail')
    localStorage.removeItem('currentUsername')
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
