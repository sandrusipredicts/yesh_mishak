import { useEffect, useState } from 'react'

import { getBackendStatus } from '../api/backend'
import StatusCard from '../components/StatusCard'

function BackendStatusPage() {
  const [status, setStatus] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let isMounted = true

    async function loadStatus() {
      try {
        const data = await getBackendStatus()
        if (isMounted) {
          setStatus(data.status)
          setError(null)
        }
      } catch (requestError) {
        if (isMounted) {
          setError(requestError)
        }
      } finally {
        if (isMounted) {
          setLoading(false)
        }
      }
    }

    loadStatus()

    return () => {
      isMounted = false
    }
  }, [])

  return (
    <main className="app-shell">
      <StatusCard error={error} loading={loading} status={status} />
    </main>
  )
}

export default BackendStatusPage
