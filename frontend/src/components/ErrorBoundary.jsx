import { Component } from 'react'
import { withTranslation } from 'react-i18next'

import { captureException } from '../monitoring/index.js'

// Class component: componentDidCatch has no hook equivalent, so this uses
// react-i18next's withTranslation HOC (not useTranslation) to get bilingual
// fallback strings.
class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, eventId: null }
    this.handleReload = this.handleReload.bind(this)
  }

  static getDerivedStateFromError() {
    return { hasError: true }
  }

  componentDidCatch(error, info) {
    // captureException is a safe no-op if monitoring never initialized (no
    // DSN, disabled environment, or init failure) -- this call can never
    // itself throw and re-trigger the boundary.
    const eventId = captureException(error, {
      contexts: {
        react: { componentStack: info?.componentStack },
      },
    })
    this.setState({ eventId: eventId || null })
  }

  handleReload() {
    window.location.reload()
  }

  render() {
    if (!this.state.hasError) {
      return this.props.children
    }

    // Intentionally minimal: no dynamic/user-supplied content is rendered
    // here (only static translated strings + an opaque event id), so this
    // fallback itself has essentially no way to throw and create a report
    // loop. If it somehow did, there is no nested boundary to catch it --
    // by design, since a boundary cannot safely catch errors from its own
    // fallback render -- and the error would surface once via the global
    // handler installed by monitoring/index.js, not repeatedly.
    const { t } = this.props

    return (
      <main className="error-boundary-fallback">
        <h1>{t('errorBoundary.title')}</h1>
        <p>{t('errorBoundary.message')}</p>
        {this.state.eventId ? (
          <p className="error-boundary-fallback__event-id">
            {t('errorBoundary.eventIdLabel')}: {this.state.eventId}
          </p>
        ) : null}
        <button type="button" onClick={this.handleReload}>
          {t('errorBoundary.reload')}
        </button>
      </main>
    )
  }
}

export default withTranslation()(ErrorBoundary)
