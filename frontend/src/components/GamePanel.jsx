import { useState } from 'react'
import { joinGame, leaveGame, extendGame, closeGame } from '../api/games'

const ACTIVE_GAME_STATUSES = new Set(['open', 'full'])

function getGameId(game) {
  return game?.id || game?.game_id || ''
}

function getParticipants(game) {
  const participants = game?.participants ?? game?.players ?? game?.game_players ?? []
  return Array.isArray(participants) ? participants : []
}

function getParticipantUserId(participant) {
  return String(participant?.user_id || participant?.id || participant?.user?.id || '')
}

function getParticipantName(participant) {
  return (
    participant?.name ||
    participant?.full_name ||
    participant?.display_name ||
    participant?.user?.name ||
    participant?.user?.full_name ||
    participant?.user?.display_name ||
    'Unknown player'
  )
}

function hasParticipantsPayload(game) {
  return (
    Array.isArray(game?.participants) ||
    Array.isArray(game?.players) ||
    Array.isArray(game?.game_players)
  )
}

function GamePanel({ game, currentUserId, onUpdate }) {
  const [error, setError] = useState('')
  const [successMessage, setSuccessMessage] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  const gameId = getGameId(game)
  const gameStatus = String(game?.status || '').toLowerCase()
  const isActiveGame = !gameStatus || ACTIVE_GAME_STATUSES.has(gameStatus)
  const participants = getParticipants(game)
  const hasParticipants = hasParticipantsPayload(game)
  const normalizedCurrentUserId = String(currentUserId || '')
  const creatorId = String(game?.created_by || '')
  const isCreator = Boolean(
    normalizedCurrentUserId && creatorId === normalizedCurrentUserId,
  )
  const isParticipant = participants.some(
    (participant) => getParticipantUserId(participant) === normalizedCurrentUserId,
  )
  const cannotAct = isLoading || !gameId || !normalizedCurrentUserId || !isActiveGame

  async function handleJoin() {
    setIsLoading(true)
    setError('')
    setSuccessMessage('')
    try {
      await joinGame(gameId, normalizedCurrentUserId)
      onUpdate?.()
    } catch {
      setError('Could not join game. Please try again.')
    } finally {
      setIsLoading(false)
    }
  }

  async function handleLeave() {
    setIsLoading(true)
    setError('')
    setSuccessMessage('')
    try {
      await leaveGame(gameId, normalizedCurrentUserId)
      onUpdate?.()
    } catch {
      setError('Could not leave game. Please try again.')
    } finally {
      setIsLoading(false)
    }
  }

  async function handleExtend() {
    setIsLoading(true)
    setError('')
    setSuccessMessage('')
    try {
      await extendGame(gameId)
      onUpdate?.()
    } catch {
      setError('Could not extend game. Please try again.')
    } finally {
      setIsLoading(false)
    }
  }

  async function handleCloseGame() {
    if (!window.confirm('Close this game? Players will no longer be able to join it.')) {
      return
    }

    setIsLoading(true)
    setError('')
    setSuccessMessage('')
    try {
      await closeGame(gameId)
      setSuccessMessage('Game closed successfully.')
      onUpdate?.()
    } catch {
      setError('Could not close game. Please try again.')
    } finally {
      setIsLoading(false)
    }
  }

  if (!game) return null

  return (
    <div className="game-panel">
      <p className="game-player-count">
        {game.players_present} / {game.max_players} players
      </p>

      {game.age_note ? (
        <p className="game-age-note">{game.age_note}</p>
      ) : null}

      {!gameId ? (
        <p className="panel-warning">This game is missing an id. Please refresh and try again.</p>
      ) : null}

      {!normalizedCurrentUserId ? (
        <p className="panel-warning">Set a current user before joining this game.</p>
      ) : null}

      {!isActiveGame ? (
        <p className="panel-closed">This game is closed.</p>
      ) : null}

      {hasParticipants ? (
        <ul className="participants-list" aria-label="Participants">
          {participants.map((participant) => {
            const participantUserId = getParticipantUserId(participant)
            const participantName = getParticipantName(participant)

            return (
              <li key={participantUserId || participantName}>
                {participantName}
              </li>
            )
          })}
        </ul>
      ) : (
        <p className="panel-warning">Participant list is not available yet.</p>
      )}

      <div className="game-actions" style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        {isActiveGame && (!hasParticipants || !isParticipant) ? (
          <button
            type="button"
            className="primary-panel-button"
            onClick={handleJoin}
            disabled={cannotAct}
          >
            I'm coming
          </button>
        ) : null}

        {isActiveGame && (!hasParticipants || isParticipant) ? (
          <button
            type="button"
            className="secondary-panel-button"
            onClick={handleLeave}
            disabled={cannotAct}
          >
            Leave
          </button>
        ) : null}

        {isActiveGame && isCreator ? (
          <button
            type="button"
            className="secondary-panel-button"
            onClick={handleExtend}
            disabled={cannotAct}
          >
            Extra round
          </button>
        ) : null}

        {isActiveGame && isCreator ? (
          <button
            type="button"
            className="danger-panel-button"
            onClick={handleCloseGame}
            disabled={cannotAct}
          >
            Close game
          </button>
        ) : null}
      </div>

      {successMessage ? <p className="panel-success">{successMessage}</p> : null}
      {error ? <p className="panel-error">{error}</p> : null}
    </div>
  )
}
// test deploy
export default GamePanel
