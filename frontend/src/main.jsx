import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import './i18n'
import App from './App.jsx'
import ErrorBoundary from './components/ErrorBoundary.jsx'
import { initMonitoring } from './monitoring/index.js'
import TestCrashTrigger from './monitoring/TestCrashTrigger.jsx'

// Initialized before the tree renders so a bootstrap-time failure (or a
// render error in App itself, once caught by ErrorBoundary below) is always
// reportable. initMonitoring() never throws -- see monitoring/client.js.
initMonitoring()

// window.__monitoringTest only exists when monitoring/index.js's dev/test
// gate allowed it (never in production) -- TestCrashTrigger itself is not
// even mounted otherwise, so there is no test-only code present in the
// production render tree at all, not just an inactive one.
const isTestTriggerAllowed = typeof window !== 'undefined' && Boolean(window.__monitoringTest)

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <ErrorBoundary>
      {isTestTriggerAllowed ? <TestCrashTrigger /> : null}
      <App />
    </ErrorBoundary>
  </StrictMode>,
)
