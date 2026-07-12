// Minimal clipboard adapter. Every call site injects this via a default
// parameter so tests can substitute a stub without touching globals.

export async function copyToClipboard(text) {
  const value = typeof text === 'string' ? text : ''

  if (!value) {
    throw new Error('Clipboard text is required')
  }

  if (
    typeof navigator !== 'undefined' &&
    typeof navigator.clipboard?.writeText === 'function'
  ) {
    try {
      await navigator.clipboard.writeText(value)
      return
    } catch {
      // Some WebViews expose the API but reject writes. Continue to the
      // DOM fallback so copy-link still works after a user gesture.
    }
  }

  if (typeof document === 'undefined' || typeof document.execCommand !== 'function') {
    throw new Error('Clipboard API unavailable')
  }

  const textarea = document.createElement('textarea')
  textarea.value = value
  textarea.setAttribute('readonly', '')
  textarea.style.position = 'fixed'
  textarea.style.top = '0'
  textarea.style.left = '-9999px'
  textarea.style.opacity = '0'

  document.body.appendChild(textarea)

  try {
    textarea.focus()
    textarea.select()
    textarea.setSelectionRange(0, textarea.value.length)

    if (!document.execCommand('copy')) {
      throw new Error('Clipboard fallback failed')
    }
  } finally {
    textarea.remove()
  }
}
