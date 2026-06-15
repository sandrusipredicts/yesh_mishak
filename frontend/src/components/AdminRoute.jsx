import { useEffect, useState } from 'react'

import { getAdminMe } from '../api/admin'
import LoginPage from './LoginPage'

function hasAccessToken() {
  return Boolean(localStorage.getItem('access_token'))
}

function clearAuthStorage() {
  localStorage.removeItem('access_token')
  localStorage.removeItem('currentUserId')
  localStorage.removeItem('currentUserName')
  localStorage.removeItem('currentUserEmail')
}

function AdminRoute({ children, onForbidden, onLogin, onUnauthorized }) {
  const [status, setStatus] = useState(() => (hasAccessToken() ? 'checking' : 'logged-out'))
  const [error, setError] = useState('')
  const [retryKey, setRetryKey] = useState(0)

  useEffect(() => {
    let isMounted = true

    async function verifyAdmin() {
      if (!hasAccessToken()) {
        setStatus('logged-out')
        return
      }

      setStatus('checking')
      setError('')

      try {
        await getAdminMe()

        if (isMounted) {
          setStatus('allowed')
        }
      } catch (verifyError) {
        if (!isMounted) {
          return
        }

        const responseStatus = verifyError.response?.status

        if (responseStatus === 401) {
          clearAuthStorage()
          onUnauthorized?.()
          setStatus('logged-out')
          return
        }

        if (responseStatus === 403) {
          onForbidden?.()
          return
        }

        setError('Could not verify admin access.')
        setStatus('error')
      }
    }

    verifyAdmin()

    return () => {
      isMounted = false
    }
  }, [onForbidden, onUnauthorized, retryKey])

  if (status === 'logged-out') {
    return (
      <LoginPage
        onLogin={(user) => {
          onLogin?.(user)
          setStatus('checking')
          setRetryKey((currentKey) => currentKey + 1)
        }}
      />
    )
  }

  if (status === 'checking') {
    return <p className="admin-route-status">Checking admin access...</p>
  }

  if (status === 'error') {
    return (
      <main className="admin-route-error">
        <p>{error}</p>
        <button type="button" onClick={() => setRetryKey((currentKey) => currentKey + 1)}>
          Retry
        </button>
      </main>
    )
  }

  return children
}

export default AdminRoute
