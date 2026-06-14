import { useState } from 'react'
import { joinGame, leaveGame, extendGame } from '../api/games'

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
  const [isLoading, setIsLoading] = useState(false)

  const gameId = getGameId(game)
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
  const cannotAct = isLoading || !gameId || !normalizedCurrentUserId

  async function handleJoin() {
    setIsLoading(true)
    setError('')
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
    try {
      await extendGame(gameId)
      onUpdate?.()
    } catch {
      setError('Could not extend game. Please try again.')
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

      <div className="game-actions">
        {hasParticipants && isParticipant ? null : (
          <button
            type="button"
            className="primary-panel-button"
            onClick={handleJoin}
            disabled={cannotAct}
          >
            I'm coming
          </button>
        )}

        {hasParticipants && !isParticipant ? null : (
          <button
            type="button"
            className="secondary-panel-button"
            onClick={handleLeave}
            disabled={cannotAct}
          >
            Leave
          </button>
        )}

        {isCreator ? (
          <button
            type="button"
            className="secondary-panel-button"
            onClick={handleExtend}
            disabled={cannotAct}
          >
            Extra round
          </button>
        ) : null}
      </div>

      {error ? <p className="panel-error">{error}</p> : null}
    </div>
  )
}

export default GamePanel
