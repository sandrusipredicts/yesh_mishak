function StatusCard({ error, loading, status }) {
  let content = 'Checking backend...'

  if (error) {
    content = 'Backend status unavailable'
  } else if (!loading) {
    content = `Backend status: ${status}`
  }

  return (
    <section className="status-panel">
      <h1>yesh_mishak</h1>
      <p className={error ? 'status-line status-error' : 'status-line'}>
        <span className="status-value">{content}</span>
      </p>
    </section>
  )
}

export default StatusCard
