import { useCallback, useState } from 'react'

import './App.css'
import LoginPage from './components/LoginPage'
import MapPage from './pages/MapPage'
import OnboardingPage from './pages/OnboardingPage'

function getStoredUser() {
  const accessToken = localStorage.getItem('access_token')
  const id = localStorage.getItem('currentUserId')

  if (!accessToken || !id) {
    return null
  }

  return {
    id,
    name: localStorage.getItem('currentUserName') || '',
    email: localStorage.getItem('currentUserEmail') || '',
  }
}

function App() {
  const [currentUser, setCurrentUser] = useState(getStoredUser)
  const [isOnboardingDone, setIsOnboardingDone] = useState(
    () => localStorage.getItem('onboarding_done') === 'true',
  )

  const handleLogout = useCallback(() => {
    localStorage.removeItem('access_token')
    localStorage.removeItem('currentUserId')
    localStorage.removeItem('currentUserName')
    localStorage.removeItem('currentUserEmail')
    setCurrentUser(null)
  }, [])

  const handleOnboardingComplete = useCallback(() => {
    setIsOnboardingDone(true)
  }, [])

  if (!currentUser) {
    return <LoginPage onLogin={setCurrentUser} />
  }

  if (!isOnboardingDone) {
    return <OnboardingPage onComplete={handleOnboardingComplete} />
  }

  return (
    <>
      <MapPage />
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
