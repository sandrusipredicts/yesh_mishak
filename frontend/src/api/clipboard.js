// Minimal clipboard adapter. Every call site injects this via a default
// parameter so tests can substitute a stub without touching globals.

export async function copyToClipboard(text) {
  if (
    typeof navigator === 'undefined' ||
    typeof navigator.clipboard?.writeText !== 'function'
  ) {
    throw new Error('Clipboard API unavailable')
  }

  await navigator.clipboard.writeText(text)
}
