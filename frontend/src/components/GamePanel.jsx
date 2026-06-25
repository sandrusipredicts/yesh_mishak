import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { joinGame, leaveGame, extendGame, closeGame } from '../api/games'
import { getStoredSessionUserId } from '../api/auth'
import { getApiErrorMessage } from '../api/errors'

const ACTIVE_GAME_STATUSES = new Set(['open', 'full'])

function normalizeUserId(value) {
  return String(value ?? '').trim().toLowerCase()
}

function getGameId(game) {
  return game?.id || game?.game_id || ''
}

function getParticipants(game) {
  const participants = game?.participants ?? game?.players ?? game?.game_players ?? []
  return Array.isArray(participants) ? participants : []
}

function getParticipantUserId(participant) {
  return normalizeUserId(participant?.user_id || participant?.id || participant?.user?.id)
}

function getParticipantName(participant, fallback) {
  return (
    participant?.username ||
    participant?.name ||
    participant?.full_name ||
    participant?.display_name ||
    participant?.user?.username ||
    participant?.user?.name ||
    participant?.user?.full_name ||
    participant?.user?.display_name ||
    fallback
  )
}

function hasParticipantsPayload(game) {
  return (
    Array.isArray(game?.participants) ||
    Array.isArray(game?.players) ||
    Array.isArray(game?.game_players)
  )
}

function parseDate(value) {
  if (!value) {
    return null
  }

  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}

function formatTime(value, locale, fallback) {
  const date = parseDate(value)
  if (!date) {
    return fallback
  }

  return new Intl.DateTimeFormat(locale, {
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

function formatDateTime(value, locale, fallback) {
  const date = parseDate(value)
  if (!date) {
    return fallback
  }

  return new Intl.DateTimeFormat(locale, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date)
}

function formatRemainingTime(milliseconds, t) {
  if (milliseconds <= 0) {
    return t('game.ended')
  }

  const totalMinutes = Math.ceil(milliseconds / 60000)
  const hours = Math.floor(totalMinutes / 60)
  const minutes = totalMinutes % 60

  if (hours && minutes) {
    return t('game.hoursMinutes', { hours, minutes })
  }

  if (hours) {
    return t('game.hours', { hours })
  }

  return t('game.minutes', { minutes })
}

function GamePanel({ game, currentUserId, onUpdate }) {
  const { i18n, t } = useTranslation()
  const [error, setError] = useState('')
  const [successMessage, setSuccessMessage] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [showCloseConfirm, setShowCloseConfirm] = useState(false)
  const [participantsToggleState, setParticipantsToggleState] = useState({
    gameId: '',
    isOpen: false,
  })
  const [now, setNow] = useState(() => Date.now())

  const locale = i18n.resolvedLanguage === 'he' ? 'he-IL' : 'en-US'
  const gameId = getGameId(game)
  const gameStatus = String(game?.status || '').toLowerCase()
  const scheduledAt = useMemo(() => parseDate(game?.scheduled_at), [game?.scheduled_at])
  const expiresAt = useMemo(() => parseDate(game?.expires_at), [game?.expires_at])
  const remainingMilliseconds = expiresAt ? expiresAt.getTime() - now : null
  const isExpiredByTime = remainingMilliseconds !== null && remainingMilliseconds <= 0
  const isUpcomingGame = scheduledAt ? scheduledAt.getTime() > now : false
  const isActionableGame = (!gameStatus || ACTIVE_GAME_STATUSES.has(gameStatus)) && !isExpiredByTime
  const isActiveGame = isActionableGame && !isUpcomingGame
  const playersPresent = Number(game?.players_present)
  const maxPlayers = Number(game?.max_players)
  const isFull = Number.isFinite(playersPresent) && Number.isFinite(maxPlayers)
    ? playersPresent >= maxPlayers
    : gameStatus === 'full'
  const participants = getParticipants(game)
  const hasParticipants = hasParticipantsPayload(game)
  const participantCount = hasParticipants
    ? participants.length
    : Number(game?.players_present ?? 0)
  const areParticipantsOpen = participantsToggleState.gameId === gameId
    ? participantsToggleState.isOpen
    : false
  const normalizedCurrentUserId = normalizeUserId(getStoredSessionUserId() || currentUserId)
  const creatorId = normalizeUserId(game?.created_by)
  const isCreator = Boolean(
    normalizedCurrentUserId && creatorId === normalizedCurrentUserId,
  )
  const isParticipant = participants.some(
    (participant) => getParticipantUserId(participant) === normalizedCurrentUserId,
  )
  const cannotJoinOrLeave = isLoading || !gameId || !normalizedCurrentUserId || !isActionableGame
  const cannotUseActiveControls = isLoading || !gameId || !normalizedCurrentUserId || !isActiveGame

  useEffect(() => {
    const refreshAt = isUpcomingGame ? scheduledAt : expiresAt

    if (!refreshAt) {
      return undefined
    }

    const refreshTimer = window.setTimeout(() => {
      setNow(Date.now())
      onUpdate?.()
    }, Math.max(0, refreshAt.getTime() - Date.now()) + 1000)

    const tickTimer = window.setInterval(() => {
      setNow(Date.now())
    }, 30000)

    return () => {
      window.clearTimeout(refreshTimer)
      window.clearInterval(tickTimer)
    }
  }, [expiresAt, isUpcomingGame, onUpdate, scheduledAt])

  async function handleJoin() {
    setIsLoading(true)
    setError('')
    setSuccessMessage('')
    try {
      await joinGame(gameId, normalizedCurrentUserId)
      await onUpdate?.()
    } catch (joinError) {
      setError(getApiErrorMessage(joinError, t('game.joinFailed')))
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
      await onUpdate?.()
    } catch (leaveError) {
      setError(getApiErrorMessage(leaveError, t('game.leaveFailed')))
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
      await onUpdate?.()
    } catch (extendError) {
      setError(getApiErrorMessage(extendError, t('game.extendFailed')))
    } finally {
      setIsLoading(false)
    }
  }

  async function handleCloseGame() {
    setShowCloseConfirm(false)
    setIsLoading(true)
    setError('')
    setSuccessMessage('')
    try {
      await closeGame(gameId)
      setSuccessMessage(t('game.closeSuccess'))
      await onUpdate?.()
    } catch (closeError) {
      setError(getApiErrorMessage(closeError, t('game.closeFailed')))
    } finally {
      setIsLoading(false)
    }
  }

  if (!game) return null

  return (
    <div className="game-panel">
      <p className="game-player-count">
        {t('game.players', { current: game.players_present, max: game.max_players })}
      </p>

      {isUpcomingGame ? (
        <dl className="game-time-list" aria-label={t('game.schedule')}>
          <div>
            <dt>{t('game.scheduled')}</dt>
            <dd>{formatDateTime(game.scheduled_at, locale, t('game.notSet'))}</dd>
          </div>
        </dl>
      ) : (
        <dl className="game-time-list" aria-label={t('game.schedule')}>
          <div>
            <dt>{t('game.start')}</dt>
            <dd>{formatTime(game.started_at, locale, t('game.notSet'))}</dd>
          </div>
          <div>
            <dt>{t('game.end')}</dt>
            <dd>{formatTime(game.expires_at, locale, t('game.notSet'))}</dd>
          </div>
          <div>
            <dt>{t('game.endsIn')}</dt>
            <dd>
              {remainingMilliseconds === null
                ? t('game.notSet')
                : formatRemainingTime(remainingMilliseconds, t)}
            </dd>
          </div>
        </dl>
      )}

      {game.age_note ? (
        <p className="game-age-note">{game.age_note}</p>
      ) : null}

      {!gameId ? (
        <p className="panel-warning">{t('game.missingId')}</p>
      ) : null}

      {!normalizedCurrentUserId ? (
        <p className="panel-warning">{t('game.missingUser')}</p>
      ) : null}

      {!isActionableGame ? (
        <p className="panel-closed">{t('game.endedMessage')}</p>
      ) : null}

      <div className="participants-section">
        <button
          type="button"
          className="participants-toggle-button"
          onClick={() =>
            setParticipantsToggleState((state) => ({
              gameId,
              isOpen: state.gameId === gameId ? !state.isOpen : true,
            }))}
          aria-expanded={areParticipantsOpen}
          aria-controls="game-participants-list"
        >
          <span>{t('game.participants', { count: participantCount })}</span>
          <span className="participants-toggle-icon" aria-hidden="true">▾</span>
        </button>

        {areParticipantsOpen && hasParticipants ? (
          <ul
            className="participants-list"
            id="game-participants-list"
            aria-label={t('game.participantsLabel')}
          >
            {participants.map((participant, index) => {
              const participantUserId = getParticipantUserId(participant)
              const participantName = getParticipantName(participant, t('game.userFallback'))

              return (
                <li key={participantUserId || `${participantName}-${index}`}>
                  {participantName}
                </li>
              )
            })}
          </ul>
        ) : null}

        {areParticipantsOpen && !hasParticipants ? (
          <p className="panel-warning">{t('game.participantsUnavailable')}</p>
        ) : null}
      </div>

      <div className="game-actions">
        {isActionableGame && (!hasParticipants || (!isParticipant && !isFull)) ? (
          <button
            type="button"
            className="primary-panel-button"
            onClick={handleJoin}
            disabled={cannotJoinOrLeave || isFull}
          >
            {t('game.join')}
          </button>
        ) : null}

        {isActionableGame && isParticipant ? (
          <button
            type="button"
            className="secondary-panel-button"
            onClick={handleLeave}
            disabled={cannotJoinOrLeave}
          >
            {t('game.leave')}
          </button>
        ) : null}

        {isActiveGame && isCreator ? (
          <button
            type="button"
            className="secondary-panel-button"
            onClick={handleExtend}
            disabled={cannotUseActiveControls}
          >
            {t('game.extend')}
          </button>
        ) : null}

        {isActiveGame && isCreator ? (
          <button
            type="button"
            className="danger-panel-button"
            onClick={() => setShowCloseConfirm(true)}
            disabled={cannotUseActiveControls}
          >
            {t('game.closeGame')}
          </button>
        ) : null}
      </div>

      {showCloseConfirm ? (
        <div className="confirm-modal-backdrop" role="presentation">
          <div className="confirm-modal" role="alertdialog" aria-modal="true" aria-labelledby="close-game-confirm-title">
            <h3 id="close-game-confirm-title">{t('game.closeConfirmTitle')}</h3>
            <p>{t('game.closeConfirm')}</p>
            <div className="confirm-modal-actions">
              <button type="button" className="secondary-modal-button" onClick={() => setShowCloseConfirm(false)}>
                {t('field.cancel')}
              </button>
              <button type="button" className="danger-modal-button" onClick={handleCloseGame}>
                {t('game.closeConfirmAction')}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {successMessage ? <p className="panel-success">{successMessage}</p> : null}
      {error ? <p className="panel-error">{error}</p> : null}
    </div>
  )
}
export default GamePanel
