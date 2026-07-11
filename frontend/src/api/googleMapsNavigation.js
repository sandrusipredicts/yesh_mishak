function getValidatedDestination(latitude, longitude) {
  if (
    latitude === null ||
    latitude === undefined ||
    longitude === null ||
    longitude === undefined ||
    (typeof latitude === 'string' && latitude.trim() === '') ||
    (typeof longitude === 'string' && longitude.trim() === '')
  ) {
    return null
  }

  const parsedLatitude = Number(latitude)
  const parsedLongitude = Number(longitude)

  if (
    !Number.isFinite(parsedLatitude) ||
    !Number.isFinite(parsedLongitude) ||
    parsedLatitude < -90 ||
    parsedLatitude > 90 ||
    parsedLongitude < -180 ||
    parsedLongitude > 180
  ) {
    return null
  }

  return `${parsedLatitude},${parsedLongitude}`
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
