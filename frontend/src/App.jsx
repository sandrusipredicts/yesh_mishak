import { useCallback, useEffect, useState } from 'react'

import './App.css'
import AdminRoute from './components/AdminRoute'
import LoginPage from './components/LoginPage'
import AdminPage from './pages/AdminPage'
import MapPage from './pages/MapPage'
import OnboardingPage from './pages/OnboardingPage'
import { getStoredSessionUserId } from './api/auth'
import { startForegroundPushNotifications } from './firebaseMessaging'

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
  const [pathname, setPathname] = useState(() => window.location.pathname)
  const [currentUser, setCurrentUser] = useState(getStoredUser)
  const [isOnboardingDone, setIsOnboardingDone] = useState(
    () => localStorage.getItem('onboarding_done') === 'true',
  )

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

    startForegroundPushNotifications().catch(() => {})
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

  if (pathname === '/admin') {
    return (
      <AdminRoute
        onForbidden={handleAdminForbidden}
        onLogin={setCurrentUser}
        onUnauthorized={handleLogout}
      >
        <AdminPage />
      </AdminRoute>
    )
  }

  if (!currentUser) {
    return <LoginPage onLogin={setCurrentUser} />
  }

  if (!isOnboardingDone) {
    return <OnboardingPage onComplete={handleOnboardingComplete} />
  }

  return (
    <>
      <MapPage currentUserId={currentUser.id} />
      <div className="auth-toolbar">
        <span>{currentUser.name || currentUser.email}</span>
        <button type="button" onClick={handleLogout}>
          Logout
        </button>
      </div>
    </>
  )
}

export default App
