import { buildFieldSharePayload } from '../utils/fieldSharePayload.js'
import { buildFieldShareUrl } from '../utils/shareLink.js'
import { buildClipboardShareText } from '../utils/clipboardShareText.js'
import { copyToClipboard } from './clipboard.js'
import { invokeNativeShare } from './nativeShare.js'
import { recordShareAction } from './shareAnalytics.js'

function trackFieldShare(result, options, recordAnalytics) {
  try {
    recordAnalytics('field', result, options)
  } catch (error) {
    console.warn('Field share analytics failed.', error?.message || error)
  }
}

// Sharing orchestrator for fields. The only entry point UI components call
// to share a field. Tries native share first; when unavailable, falls back
// to copying the readable share message plus the canonical URL to the
// clipboard so the user can paste it into WhatsApp or any other app.
export async function shareField(
  { field, t },
  { invokeShare = invokeNativeShare, copyText = copyToClipboard, recordAnalytics = recordShareAction } = {},
) {
  const payload = buildFieldSharePayload({ field, t })

  if (!payload) {
    const result = { outcome: 'unavailable', mechanism: 'none', reason: 'invalid-resource' }
    trackFieldShare(result, { mechanism: 'native_share' }, recordAnalytics)
    return result
  }

  const nativeResult = await invokeShare(payload)

  if (nativeResult.outcome !== 'unavailable') {
    trackFieldShare(nativeResult, undefined, recordAnalytics)
    return nativeResult
  }

  // Native share is unavailable — fall back to clipboard with full message.
  try {
    await copyText(buildClipboardShareText(payload))
    const result = { outcome: 'copied', mechanism: 'clipboard' }
    trackFieldShare(result, undefined, recordAnalytics)
    return result
  } catch {
    const result = { outcome: 'failed', mechanism: 'clipboard', reason: 'clipboard-write-failed' }
    trackFieldShare(result, undefined, recordAnalytics)
    return result
  }
}

export async function copyFieldLink(
  field,
  { copyText = copyToClipboard, recordAnalytics = recordShareAction } = {},
) {
  const url = buildFieldShareUrl(field?.id)

  if (!url) {
    const result = { outcome: 'unavailable', mechanism: 'none', reason: 'invalid-resource' }
    trackFieldShare(result, { mechanism: 'copy_link' }, recordAnalytics)
    return result
  }

  try {
    await copyText(url)
    const result = { outcome: 'copied', mechanism: 'clipboard', url }
    trackFieldShare(result, { mechanism: 'copy_link' }, recordAnalytics)
    return result
  } catch {
    const result = { outcome: 'failed', mechanism: 'clipboard', reason: 'clipboard-write-failed' }
    trackFieldShare(result, { mechanism: 'copy_link' }, recordAnalytics)
    return result
  }
}
