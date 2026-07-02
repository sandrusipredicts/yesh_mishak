import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { getAdminMe } from '../api/admin'
import { clearSession, getToken } from '../api/sessionStorage'
import LoginPage from './LoginPage'

function hasAccessToken() {
  return Boolean(getToken())
}

function AdminRoute({ children, onForbidden, onLogin, onUnauthorized }) {
  const { t } = useTranslation()
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
          clearSession().catch((cleanupError) => {
            console.warn('Session cleanup after admin 401 failed.', cleanupError)
          })
          onUnauthorized?.()
          setStatus('logged-out')
          return
        }

        if (responseStatus === 403) {
          onForbidden?.()
          return
        }

        setError(t('admin.verifyAccessFailed'))
        setStatus('error')
      }
    }

    verifyAdmin()

    return () => {
      isMounted = false
    }
  }, [onForbidden, onUnauthorized, retryKey, t])

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
    return <p className="admin-route-status">{t('admin.checkingAccess')}</p>
  }

  if (status === 'error') {
    return (
      <main className="admin-route-error">
        <p>{error}</p>
        <button type="button" onClick={() => setRetryKey((currentKey) => currentKey + 1)}>
          {t('admin.retry')}
        </button>
      </main>
    )
  }

  return children
}

export default AdminRoute
