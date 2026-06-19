import { useTranslation } from 'react-i18next'

function StatusCard({ error, loading, status }) {
  const { t } = useTranslation()
  let content = t('backend.checking')

  if (error) {
    content = t('backend.unavailable')
  } else if (!loading) {
    content = t('backend.status', { status })
  }

  return (
    <section className="status-panel">
      <h1>{t('app.name')}</h1>
      <p className={error ? 'status-line status-error' : 'status-line'}>
        <span className="status-value">{content}</span>
      </p>
    </section>
  )
}

export default StatusCard
