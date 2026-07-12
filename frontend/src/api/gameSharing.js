import { buildGameSharePayload } from '../utils/gameSharePayload.js'
import { invokeNativeShare } from './nativeShare.js'

// Sharing orchestrator (docs/native-sharing-architecture.md §4): the only
// entry point UI components call to share a game. It owns nothing itself —
// it builds the payload through the shared factory and hands off to the
// existing Native Share adapter from ISSUE-283. Components must not call
// buildGameSharePayload or invokeNativeShare directly.
export async function shareGame({ game, fieldName, locale, t }, { invokeShare = invokeNativeShare } = {}) {
  const payload = buildGameSharePayload({ game, fieldName, locale, t })

  if (!payload) {
    return { outcome: 'unavailable', mechanism: 'native-share', reason: 'invalid-resource' }
  }

  return invokeShare(payload)
}
