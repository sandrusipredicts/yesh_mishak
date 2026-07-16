const INSTALLATION_ID_KEY = 'push_installation_id'

function hasLocalStorage() {
  return typeof localStorage !== 'undefined'
}

function generateUuid() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }

  // Fallback for environments without crypto.randomUUID (e.g. older WebViews).
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (char) => {
    const random = (Math.random() * 16) | 0
    const value = char === 'x' ? random : (random & 0x3) | 0x8
    return value.toString(16)
  })
}

// Not a hardware identifier: a random UUID scoped to this app installation,
// used only to reconcile a rotated FCM token with the row it replaces. Reset
// naturally on uninstall/reinstall since it lives in the same WebView storage
// used for other non-sensitive session metadata (sessionStorage.js).
export function getOrCreateInstallationId() {
  if (!hasLocalStorage()) {
    return null
  }

  const existing = localStorage.getItem(INSTALLATION_ID_KEY)
  if (existing) {
    return existing
  }

  const generated = generateUuid()
  localStorage.setItem(INSTALLATION_ID_KEY, generated)
  return generated
}
