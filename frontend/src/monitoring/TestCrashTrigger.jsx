import { useEffect, useState } from 'react'

// Manual-verification-only. A React Error Boundary only catches errors
// thrown during render/lifecycle -- a plain `throw` from a devtools/test
// script does not go through React at all, so this tiny component exists
// purely to turn a test trigger into a real render-phase throw. It is only
// ever mounted when window.__monitoringTest already exists (see main.jsx),
// which itself is only ever set by monitoring/index.js's isTestTriggerAllowed()
// gate -- never in production.
function TestCrashTrigger() {
  const [shouldThrow, setShouldThrow] = useState(false)

  useEffect(() => {
    if (typeof window === 'undefined' || !window.__monitoringTest) {
      return undefined
    }
    window.__monitoringTest.triggerReactRenderError = () => setShouldThrow(true)
    return () => {
      delete window.__monitoringTest.triggerReactRenderError
    }
  }, [])

  if (shouldThrow) {
    throw new Error('[monitoring] test React render error (manual verification only)')
  }

  return null
}

export default TestCrashTrigger
