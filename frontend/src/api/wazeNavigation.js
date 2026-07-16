import { AppLauncher } from '@capacitor/app-launcher'
import { Capacitor } from '@capacitor/core'
import { parseValidCoordinates } from '../utils/coordinates'

const WAZE_SCHEME = 'waze://'

function getValidatedDestination(latitude, longitude) {
  const coordinates = parseValidCoordinates(latitude, longitude)
  if (!coordinates) {
    return null
  }

  return `${coordinates.latitude},${coordinates.longitude}`
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
