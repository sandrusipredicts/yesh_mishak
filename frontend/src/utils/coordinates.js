export function parseValidCoordinates(latitude, longitude) {
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

  return {
    latitude: parsedLatitude,
    longitude: parsedLongitude,
  }
}
