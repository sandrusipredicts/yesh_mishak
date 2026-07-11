import { Capacitor } from '@capacitor/core'
import { Share } from '@capacitor/share'

import { CANONICAL_APP_LINK_HOST } from '../utils/appLinkRoutes.js'

const SUPPORTED_PLATFORMS = new Set(['android', 'ios', 'web'])

function buildResult(outcome, details = {}) {
  return {
    outcome,
    mechanism: 'native-share',
    ...details,
  }
}

function normalizePayload(payload) {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    return null
  }

  const title = typeof payload.title === 'string' ? payload.title : undefined
  const text = typeof payload.text === 'string' ? payload.text : undefined
  const url = typeof payload.url === 'string' ? payload.url : ''

  let parsedUrl
  try {
    parsedUrl = new URL(url)
  } catch {
    return null
  }

  if (parsedUrl.protocol !== 'https:' || parsedUrl.hostname !== CANONICAL_APP_LINK_HOST) {
    return null
  }

  return {
    ...(title ? { title } : {}),
    ...(text ? { text } : {}),
    url: parsedUrl.toString(),
  }
}

function isCancellation(error) {
  const name = String(error?.name ?? '').toLowerCase()
  const message = String(error?.message ?? error ?? '').toLowerCase()

  return name === 'aborterror' || message.includes('cancel') || message.includes('abort')
}

export async function invokeNativeShare(
  payload,
  {
    shareApi = Share,
    getPlatform = () => Capacitor.getPlatform(),
  } = {},
) {
  let platform
  try {
    platform = getPlatform()
  } catch {
    return buildResult('unavailable', { reason: 'unsupported-platform' })
  }

  if (!SUPPORTED_PLATFORMS.has(platform)) {
    return buildResult('unavailable', { reason: 'unsupported-platform' })
  }

  const shareOptions = normalizePayload(payload)
  if (!shareOptions) {
    return buildResult('failed', { reason: 'invalid-payload' })
  }

  try {
    const availability = await shareApi.canShare()
    if (!availability?.value) {
      return buildResult('unavailable', { reason: 'share-api-unavailable' })
    }
  } catch {
    return buildResult('unavailable', { reason: 'share-api-unavailable' })
  }

  try {
    await shareApi.share(shareOptions)
    return buildResult('shared')
  } catch (error) {
    if (isCancellation(error)) {
      return buildResult('cancelled')
    }

    return buildResult('failed', { reason: 'share-invocation-failed' })
  }
}
