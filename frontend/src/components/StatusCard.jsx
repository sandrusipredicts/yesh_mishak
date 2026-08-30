import { useTranslation } from 'react-i18next'
import useBusinessBranding from '../branding/useBusinessBranding'

function StatusCard({ error, loading, status }) {
  const { t } = useTranslation()
  const { businessName } = useBusinessBranding()
  let content = t('backend.checking')

  if (error) {
    content = t('backend.unavailable')
  } else if (!loading) {
    content = t('backend.status', { status })
  }

  return (
    <section className="status-panel">
      <h1>{businessName}</h1>
      <p className={error ? 'status-line status-error' : 'status-line'}>
        <span className="status-value">{content}</span>
      </p>
    </section>
  )
}

export default StatusCard
