import { useState } from 'react'
import { MapPin } from 'lucide-react'
import GamePanel from './GamePanel'
import OpenGameModal from './OpenGameModal'

function formatBoolean(value) {
  if (value === true) {
    return 'Yes'
  }

  if (value === false) {
    return 'No'
  }

  return 'Not specified'
}

function getActiveGame(field) {
  return field?.active_game ?? field?.activeGame ?? null
}

function getUpcomingGames(field) {
  const upcomingGames = field?.upcoming_games ?? field?.upcomingGames ?? []
  return Array.isArray(upcomingGames) ? upcomingGames : []
}

function getPlayerCount(activeGame) {
  if (!activeGame) {
    return null
  }

  const playersPresent = activeGame.players_present
  const maxPlayers = activeGame.max_players

  if (playersPresent === undefined || maxPlayers === undefined) {
    return null
  }

  return `${playersPresent} מתוך ${maxPlayers} שחקנים`
}

function formatScheduledAt(value) {
  if (!value) {
    return 'מועד לא נקבע'
  }

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return 'מועד לא תקין'
  }

  return new Intl.DateTimeFormat('he-IL', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date)
}

function getWaterCoolerValue(field) {
  return field.has_water_cooler ?? field.has_water
}

function getNavigationCoordinates(field) {
  const latitude = Number(field?.lat ?? field?.latitude)
  const longitude = Number(field?.lng ?? field?.longitude)

  if (
    !Number.isFinite(latitude) ||
    !Number.isFinite(longitude) ||
    latitude < -90 ||
    latitude > 90 ||
    longitude < -180 ||
    longitude > 180
  ) {
    return null
  }

  return { latitude, longitude }
}

function FieldDetailsPanel({ field, onClose, onGameCreated, currentUserId }) {
  const [isOpenGameModalOpen, setIsOpenGameModalOpen] = useState(false)
  const [isNavigationModalOpen, setIsNavigationModalOpen] = useState(false)

  if (!field) {
    return null
  }

  const activeGame = getActiveGame(field)
  const upcomingGames = getUpcomingGames(field)
  const playerCount = getPlayerCount(activeGame)
  const status = field.approval_status ?? field.status ?? 'Not specified'
  const isPending = String(status).toLowerCase() === 'pending'
  const navigationCoordinates = getNavigationCoordinates(field)

  function openNavigation(provider) {
    if (!navigationCoordinates) {
      setIsNavigationModalOpen(false)
      return
    }

    const { latitude, longitude } = navigationCoordinates
    const destination = `${latitude},${longitude}`
    const url =
      provider === 'waze'
        ? `https://waze.com/ul?ll=${destination}&navigate=yes`
        : `https://www.google.com/maps/dir/?api=1&destination=${destination}`

    window.open(url, '_blank', 'noopener,noreferrer')
    setIsNavigationModalOpen(false)
  }

  function handleGameStateChanged() {
    return onGameCreated?.(field.id)
  }

  return (
    <aside className="field-details-panel" aria-label="Field details">
      <button className="panel-close-button" type="button" onClick={onClose} aria-label="Close">
        x
      </button>

      <div className="panel-header">
        <h2>{field.name ?? 'Unnamed field'}</h2>
        {isPending ? <span className="approval-badge">Pending VAR approval</span> : null}
      </div>

      <dl className="field-details-list">
        <div>
          <dt>Surface type</dt>
          <dd>{field.surface_type ?? 'Not specified'}</dd>
        </div>
        <div>
          <dt>Has nets</dt>
          <dd>{formatBoolean(field.has_nets)}</dd>
        </div>
        <div>
          <dt>Has water cooler</dt>
          <dd>{formatBoolean(getWaterCoolerValue(field))}</dd>
        </div>
        <div>
          <dt>Opening hours</dt>
          <dd>{field.opening_hours ?? 'Not specified'}</dd>
        </div>
        <div>
          <dt>Notes</dt>
          <dd>{field.notes ?? 'No notes'}</dd>
        </div>
        <div>
          <dt>Status</dt>
          <dd>{status}</dd>
        </div>
      </dl>

      {activeGame ? (
        <div className="active-game-summary">
          <p>{playerCount ?? 'Active game available'}</p>
          <GamePanel
            game={activeGame}
            currentUserId={currentUserId}
            onUpdate={handleGameStateChanged}
          />
        </div>
      ) : null}

      {upcomingGames.length ? (
        <section className="upcoming-games-section" aria-labelledby="upcoming-games-title">
          <h3 id="upcoming-games-title">משחקים עתידיים</h3>
          <div className="upcoming-games-list">
            {upcomingGames.map((game) => (
              <article className="upcoming-game-card" key={game.id}>
                <p>{formatScheduledAt(game.scheduled_at)}</p>
                <GamePanel
                  game={game}
                  currentUserId={currentUserId}
                  onUpdate={handleGameStateChanged}
                />
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {!activeGame ? (
        <button
          className="primary-panel-button"
          type="button"
          onClick={() => setIsOpenGameModalOpen(true)}
        >
          Open Game
        </button>
      ) : null}

      {navigationCoordinates ? (
        <button
          className="primary-panel-button navigation-panel-button"
          type="button"
          onClick={() => setIsNavigationModalOpen(true)}
        >
          <MapPin size={18} aria-hidden="true" />
          <span>נווט למגרש</span>
        </button>
      ) : null}

      {isOpenGameModalOpen ? (
        <OpenGameModal
          field={field}
          onClose={() => setIsOpenGameModalOpen(false)}
          onCreated={handleGameStateChanged}
        />
      ) : null}

      {isNavigationModalOpen && navigationCoordinates ? (
        <div className="modal-backdrop" role="presentation">
          <section
            className="navigation-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="navigation-modal-title"
          >
            <button
              className="modal-close-button"
              type="button"
              onClick={() => setIsNavigationModalOpen(false)}
              aria-label="Close"
            >
              x
            </button>

            <h2 id="navigation-modal-title">פתח ניווט</h2>

            <div className="navigation-options">
              <button
                className="navigation-option-button waze"
                type="button"
                onClick={() => openNavigation('waze')}
              >
                <span className="navigation-provider-dot" aria-hidden="true" />
                Waze
              </button>
              <button
                className="navigation-option-button google"
                type="button"
                onClick={() => openNavigation('google')}
              >
                <span className="navigation-provider-dot" aria-hidden="true" />
                Google Maps
              </button>
              <button
                className="navigation-cancel-button"
                type="button"
                onClick={() => setIsNavigationModalOpen(false)}
              >
                ביטול
              </button>
            </div>
          </section>
        </div>
      ) : null}
    </aside>
  )
}

export default FieldDetailsPanel
