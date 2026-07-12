// Product rule (allowlist, not denylist): a game may be shared only while
// a recipient could still plausibly participate in it, now or later. Add a
// status here to make it shareable — e.g. a future 'scheduled' status —
// rather than special-casing terminal statuses elsewhere. Everything not
// listed is treated as non-shareable by default, so a new terminal status
// (or one nobody has thought of yet) is safely hidden without a code change.
const SHAREABLE_GAME_STATUSES = new Set(['open', 'full'])

export function isGameShareable(game) {
  const status = String(game?.status || '').toLowerCase()
  return SHAREABLE_GAME_STATUSES.has(status)
}
