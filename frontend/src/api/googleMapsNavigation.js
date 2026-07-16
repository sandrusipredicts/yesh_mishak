import { parseValidCoordinates } from '../utils/coordinates'

function getValidatedDestination(latitude, longitude) {
  const coordinates = parseValidCoordinates(latitude, longitude)
  if (!coordinates) {
    return null
  }

  return `${coordinates.latitude},${coordinates.longitude}`
}

export function buildGoogleMapsNavigationUrl(latitude, longitude) {
  const destination = getValidatedDestination(latitude, longitude)
  if (!destination) {
    return null
  }

  return `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(destination)}`
}

export function launchGoogleMapsNavigation(latitude, longitude) {
  const url = buildGoogleMapsNavigationUrl(latitude, longitude)
  if (!url) {
    return { opened: false, reason: 'invalid_coordinates' }
  }

  try {
    window.open(url, '_blank', 'noopener,noreferrer')
    return { opened: true, mechanism: 'https' }
  } catch {
    return { opened: false, reason: 'launch_failed' }
  }
}
