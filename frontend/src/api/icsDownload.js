// Web fallback for "Add to calendar": downloads a generated .ics file
// rather than requiring a native plugin. Every call site injects
// `createObjectUrl`/`revokeObjectUrl` via default parameters so tests can
// substitute stubs without touching real DOM globals — same pattern as
// api/clipboard.js.

function hasDom() {
  return typeof document !== 'undefined' && typeof document.createElement === 'function'
}

export function downloadIcsFile(
  icsContent,
  filename,
  {
    createObjectUrl = (blob) => URL.createObjectURL(blob),
    revokeObjectUrl = (url) => URL.revokeObjectURL(url),
  } = {},
) {
  if (!hasDom() || typeof icsContent !== 'string' || !icsContent) {
    return false
  }

  const blob = new Blob([icsContent], { type: 'text/calendar;charset=utf-8' })
  const url = createObjectUrl(blob)

  try {
    const link = document.createElement('a')
    link.href = url
    link.download = filename || 'event.ics'
    link.rel = 'noopener'
    document.body.appendChild(link)
    link.click()
    link.remove()
    return true
  } finally {
    // Deferred so the browser has a chance to start the download from the
    // blob: URL before it is revoked.
    setTimeout(() => revokeObjectUrl(url), 0)
  }
}
