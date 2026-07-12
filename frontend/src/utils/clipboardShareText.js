// Combines a share payload's text and URL into a single pasteable string.
// The URL is appended only if it is not already present in the text,
// preventing duplication when someone manually pasted it.
export function buildClipboardShareText(payload) {
  const text = typeof payload?.text === 'string' ? payload.text.trim() : ''
  const url = typeof payload?.url === 'string' ? payload.url.trim() : ''

  if (!url) {
    return text || ''
  }

  if (!text) {
    return url
  }

  if (text.includes(url)) {
    return text
  }

  return `${text}\n${url}`
}
