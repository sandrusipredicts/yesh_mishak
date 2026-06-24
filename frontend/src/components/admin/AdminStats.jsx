import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { getAdminStats } from '../../api/admin'

const STAT_ITEMS = [
  { key: 'verified_fields', labelKey: 'admin.verifiedFields' },
  { key: 'pending_fields', labelKey: 'admin.pendingFields' },
  { key: 'active_games', labelKey: 'admin.activeGamesStat' },
  { key: 'total_users', labelKey: 'admin.totalUsers' },
]

function AdminStats() {
  const { t } = useTranslation()
  const [stats, setStats] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')
  const [retryKey, setRetryKey] = useState(0)

  useEffect(() => {
    let isMounted = true

    async function loadStats() {
      setIsLoading(true)
      setError('')

      try {
        const data = await getAdminStats()

        if (isMounted) {
          setStats(data)
        }
      } catch {
        if (isMounted) {
          setError(t('admin.loadStatsFailed'))
        }
      } finally {
        if (isMounted) {
          setIsLoading(false)
        }
      }
    }

    loadStats()

    return () => {
      isMounted = false
    }
  }, [retryKey, t])

  if (isLoading) {
    return <p className="admin-stats-status">{t('admin.loadingStats')}</p>
  }

  if (error) {
    return (
      <div className="admin-stats-error">
        <p>{error}</p>
        <button type="button" onClick={() => setRetryKey((k) => k + 1)}>{t('admin.retry')}</button>
      </div>
    )
  }

  return (
    <div className="admin-stats-grid">
      {STAT_ITEMS.map((item) => (
        <article className="admin-stat-card" key={item.key}>
          <span>{t(item.labelKey)}</span>
          <strong>{stats?.[item.key] ?? ''}</strong>
        </article>
      ))}
    </div>
  )
}

export default AdminStats
