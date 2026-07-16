import { buildGameSharePayload } from '../utils/gameSharePayload.js'
import { buildGameShareUrl } from '../utils/shareLink.js'
import { buildClipboardShareText } from '../utils/clipboardShareText.js'
import { copyToClipboard } from './clipboard.js'
import { invokeNativeShare } from './nativeShare.js'
import { recordShareAction } from './shareAnalytics.js'

function trackGameShare(result, options, recordAnalytics) {
  try {
    recordAnalytics('game', result, options)
  } catch (error) {
    console.warn('Game share analytics failed.', error?.message || error)
  }
}

// Sharing orchestrator for games. The only entry point UI components call
// to share a game. Tries native share first; when unavailable, falls back
// to copying the readable share message plus the canonical URL to the
// clipboard — identical fallback policy to fieldSharing.js.
export async function shareGame(
  { game, fieldName, locale, t },
  { invokeShare = invokeNativeShare, copyText = copyToClipboard, recordAnalytics = recordShareAction } = {},
) {
  const payload = buildGameSharePayload({ game, fieldName, locale, t })

  if (!payload) {
    const result = { outcome: 'unavailable', mechanism: 'none', reason: 'invalid-resource' }
    trackGameShare(result, { mechanism: 'native_share' }, recordAnalytics)
    return result
  }

  const nativeResult = await invokeShare(payload)

  if (nativeResult.outcome !== 'unavailable') {
    trackGameShare(nativeResult, undefined, recordAnalytics)
    return nativeResult
  }

  // Native share is unavailable — fall back to clipboard with full message.
  try {
    await copyText(buildClipboardShareText(payload))
    const result = { outcome: 'copied', mechanism: 'clipboard' }
    trackGameShare(result, undefined, recordAnalytics)
    return result
  } catch {
    const result = { outcome: 'failed', mechanism: 'clipboard', reason: 'clipboard-write-failed' }
    trackGameShare(result, undefined, recordAnalytics)
    return result
  }
}

export async function copyGameLink(
  game,
  { copyText = copyToClipboard, recordAnalytics = recordShareAction } = {},
) {
  const url = buildGameShareUrl(game?.id)

  if (!url) {
    const result = { outcome: 'unavailable', mechanism: 'none', reason: 'invalid-resource' }
    trackGameShare(result, { mechanism: 'copy_link' }, recordAnalytics)
    return result
  }

  try {
    await copyText(url)
    const result = { outcome: 'copied', mechanism: 'clipboard', url }
    trackGameShare(result, { mechanism: 'copy_link' }, recordAnalytics)
    return result
  } catch {
    const result = { outcome: 'failed', mechanism: 'clipboard', reason: 'clipboard-write-failed' }
    trackGameShare(result, { mechanism: 'copy_link' }, recordAnalytics)
    return result
  }
}
