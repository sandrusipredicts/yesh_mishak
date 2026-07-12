import { buildGameSharePayload } from '../utils/gameSharePayload.js'
import { buildClipboardShareText } from '../utils/clipboardShareText.js'
import { copyToClipboard } from './clipboard.js'
import { invokeNativeShare } from './nativeShare.js'

// Sharing orchestrator for games. The only entry point UI components call
// to share a game. Tries native share first; when unavailable, falls back
// to copying the readable share message plus the canonical URL to the
// clipboard — identical fallback policy to fieldSharing.js.
export async function shareGame(
  { game, fieldName, locale, t },
  { invokeShare = invokeNativeShare, copyText = copyToClipboard } = {},
) {
  const payload = buildGameSharePayload({ game, fieldName, locale, t })

  if (!payload) {
    return { outcome: 'unavailable', mechanism: 'none', reason: 'invalid-resource' }
  }

  const nativeResult = await invokeShare(payload)

  if (nativeResult.outcome !== 'unavailable') {
    return nativeResult
  }

  // Native share is unavailable — fall back to clipboard with full message.
  try {
    await copyText(buildClipboardShareText(payload))
    return { outcome: 'copied', mechanism: 'clipboard' }
  } catch {
    return { outcome: 'failed', mechanism: 'clipboard', reason: 'clipboard-write-failed' }
  }
}
