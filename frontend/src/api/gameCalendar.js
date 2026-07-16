import { buildGameCalendarPayload } from '../utils/gameCalendarPayload.js'
import { buildIcsEvent, buildIcsFilename } from '../utils/icsEvent.js'
import { openCalendarEventPrompt } from './nativeCalendar.js'
import { downloadIcsFile } from './icsDownload.js'

// Calendar orchestrator for games (E07-01). The only entry point UI
// components call to add a game to the device calendar — mirrors
// api/gameSharing.js's and api/gameReminders.js's role. Tries the native
// event-editor prompt first; when no native calendar integration is
// available (web, or a native runtime without the plugin), falls back to
// downloading an .ics file, matching the native-then-fallback shape
// already used for sharing.
export async function addGameToCalendar(
  { game, fieldName, fieldLat, fieldLng, locale, t },
  { openPrompt = openCalendarEventPrompt, download = downloadIcsFile } = {},
) {
  const payload = buildGameCalendarPayload({ game, fieldName, fieldLat, fieldLng, locale, t })

  if (!payload) {
    return { outcome: 'unavailable', reason: 'invalid-resource' }
  }

  const nativeResult = await openPrompt(payload)

  if (nativeResult.outcome !== 'unsupported') {
    return nativeResult
  }

  const icsContent = buildIcsEvent(payload, { gameId: game?.id })
  if (!icsContent) {
    return { outcome: 'unavailable', reason: 'invalid-resource' }
  }

  const downloaded = download(icsContent, buildIcsFilename(game?.id))
  return downloaded
    ? { outcome: 'downloaded' }
    : { outcome: 'failed', reason: 'download-failed' }
}
