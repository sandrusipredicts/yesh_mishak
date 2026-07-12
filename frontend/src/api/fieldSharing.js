import { buildFieldSharePayload } from '../utils/fieldSharePayload.js'
import { buildFieldShareUrl } from '../utils/shareLink.js'
import { buildClipboardShareText } from '../utils/clipboardShareText.js'
import { copyToClipboard } from './clipboard.js'
import { invokeNativeShare } from './nativeShare.js'

// Sharing orchestrator for fields. The only entry point UI components call
// to share a field. Tries native share first; when unavailable, falls back
// to copying the readable share message plus the canonical URL to the
// clipboard so the user can paste it into WhatsApp or any other app.
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

  // Native share is unavailable — fall back to clipboard with full message.
  try {
    await copyText(buildClipboardShareText(payload))
    return { outcome: 'copied', mechanism: 'clipboard' }
  } catch {
    return { outcome: 'failed', mechanism: 'clipboard', reason: 'clipboard-write-failed' }
  }
}

export async function copyFieldLink(
  field,
  { copyText = copyToClipboard } = {},
) {
  const url = buildFieldShareUrl(field?.id)

  if (!url) {
    return { outcome: 'unavailable', mechanism: 'none', reason: 'invalid-resource' }
  }

  try {
    await copyText(url)
    return { outcome: 'copied', mechanism: 'clipboard', url }
  } catch {
    return { outcome: 'failed', mechanism: 'clipboard', reason: 'clipboard-write-failed' }
  }
}
