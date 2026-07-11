import { AppLauncher } from '@capacitor/app-launcher'
import { Capacitor } from '@capacitor/core'

const WAZE_SCHEME = 'waze://'

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

export function buildWazeNavigationUrls(latitude, longitude) {
  const destination = getValidatedDestination(latitude, longitude)
  if (!destination) {
    return null
  }

  const query = `ll=${destination}&navigate=yes`
  return {
    nativeUrl: `${WAZE_SCHEME}?${query}`,
    httpsUrl: `https://waze.com/ul?${query}`,
  }
}

function openWebUrl(url) {
  try {
    window.open(url, '_blank', 'noopener,noreferrer')
    return true
  } catch {
    return false
  }
}

export async function launchWazeNavigation(latitude, longitude) {
  const urls = buildWazeNavigationUrls(latitude, longitude)
  if (!urls) {
    return { opened: false, reason: 'invalid_coordinates' }
  }

  if (!Capacitor.isNativePlatform() || !Capacitor.isPluginAvailable('AppLauncher')) {
    return openWebUrl(urls.httpsUrl)
      ? { opened: true, mechanism: 'https' }
      : { opened: false, reason: 'launch_failed' }
  }

  try {
    const { value: canOpenNative } = await AppLauncher.canOpenUrl({ url: WAZE_SCHEME })
    if (canOpenNative) {
      const { completed } = await AppLauncher.openUrl({ url: urls.nativeUrl })
      if (completed) {
        return { opened: true, mechanism: 'native' }
      }
    }
  } catch {
    // Continue to the supported Waze HTTPS fallback.
  }

  try {
    const { completed } = await AppLauncher.openUrl({ url: urls.httpsUrl })
    return completed
      ? { opened: true, mechanism: 'https' }
      : { opened: false, reason: 'launch_failed' }
  } catch {
    return { opened: false, reason: 'launch_failed' }
  }
}
