import { AppLauncher } from '@capacitor/app-launcher'
import { Capacitor } from '@capacitor/core'
import { parseValidCoordinates } from '../utils/coordinates.js'

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

  // Waze's documented universal link is the only launch target. Android routes
  // it into the installed Waze app with the destination intact; the waze://
  // custom scheme opens the app but drops the ll/navigate parameters.
  return {
    httpsUrl: `https://waze.com/ul?ll=${encodeURIComponent(destination)}&navigate=yes`,
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
    const { completed } = await AppLauncher.openUrl({ url: urls.httpsUrl })
    return completed
      ? { opened: true, mechanism: 'native' }
      : { opened: false, reason: 'launch_failed' }
  } catch {
    return { opened: false, reason: 'launch_failed' }
  }
}
