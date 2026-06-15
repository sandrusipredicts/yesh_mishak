import { useEffect, useState } from 'react'

import { getAdminStats } from '../../api/admin'

const STAT_ITEMS = [
  { key: 'verified_fields', label: 'Verified fields' },
  { key: 'pending_fields', label: 'Pending fields' },
  { key: 'active_games', label: 'Active games' },
  { key: 'total_users', label: 'Total users' },
]

function AdminStats() {
  const [stats, setStats] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')

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
          setError('Could not load admin stats.')
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
  }, [])

  if (isLoading) {
    return <p className="admin-stats-status">Loading stats...</p>
  }

  if (error) {
    return <p className="admin-stats-error">{error}</p>
  }

  return (
    <div className="admin-stats-grid">
      {STAT_ITEMS.map((item) => (
        <article className="admin-stat-card" key={item.key}>
          <span>{item.label}</span>
          <strong>{stats?.[item.key] ?? ''}</strong>
        </article>
      ))}
    </div>
  )
}

export default AdminStats
