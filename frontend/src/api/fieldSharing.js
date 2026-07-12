import { buildFieldSharePayload } from '../utils/fieldSharePayload.js'
import { copyToClipboard } from './clipboard.js'
import { invokeNativeShare } from './nativeShare.js'

// Sharing orchestrator for fields. The only entry point UI components call
// to share a field. Tries native share first; when unavailable, falls back
// to copying the canonical URL to the clipboard.
export async function shareField(
  { field, t },
  { invokeShare = invokeNativeShare, copyText = copyToClipboard } = {},
) {
  const payload = buildFieldSharePayload({ field, t })

  if (!payload) {
    return { outcome: 'unavailable', mechanism: 'none', reason: 'invalid-resource' }
  }

  const nativeResult = await invokeShare(payload)

  if (nativeResult.outcome !== 'unavailable') {
    return nativeResult
  }

  // Native share is unavailable — fall back to clipboard.
  try {
    await copyText(payload.url)
    return { outcome: 'copied', mechanism: 'clipboard' }
  } catch {
    return { outcome: 'failed', mechanism: 'clipboard', reason: 'clipboard-write-failed' }
  }
}
